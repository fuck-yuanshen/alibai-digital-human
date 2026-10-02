# -*- coding: utf-8 -*-
"""
@author:XuMing(xuming624@qq.com)
@description: Server
"""
import json

from aiohttp import web
import aiohttp
import aiohttp_cors
from aiortc import RTCPeerConnection, RTCSessionDescription, RTCConfiguration
from aiortc.rtcrtpsender import RTCRtpSender

import argparse
import asyncio
import uuid
import os
from typing import Dict

from src.webrtc import HumanPlayer
from src.basereal import BaseReal, prepare_enhanced_frame_cache_for_frames
from src.llm import llm_response
from src.settings import get_system_prompt, set_system_prompt
from src.log import get_log_file_path, logger
from src.get_file import http_get
from src.config import get_avatar_download_config, get_avatars_config, get_avatar_config

nerfreals: Dict[int, BaseReal] = {}  # sessionid:BaseReal
opt = None
model = None
avatar = None

# webrtc
pcs = set()

pwd_path = os.path.abspath(os.path.dirname(__file__))


def set_video_bitrate(sdp: str, bitrate_kbps: int) -> str:
    """Add a video bandwidth hint to SDP without taking over aiortc's sender pipeline."""
    if bitrate_kbps <= 0:
        return sdp

    lines = sdp.splitlines()
    output = []
    in_video = False
    inserted = False

    for line in lines:
        if line.startswith("m="):
            if in_video and not inserted:
                output.append(f"b=AS:{bitrate_kbps}")
            in_video = line.startswith("m=video")
            inserted = False
            output.append(line)
            continue

        if in_video and (line.startswith("b=AS:") or line.startswith("b=TIAS:")):
            continue

        output.append(line)
        if in_video and not inserted and line.startswith("c="):
            output.append(f"b=AS:{bitrate_kbps}")
            inserted = True
#baidu_test
    if in_video and not inserted:
        output.append(f"b=AS:{bitrate_kbps}")

    return "\r\n".join(output) + "\r\n"


async def force_periodic_keyframes(video_sender, sessionid: int, interval: float):
    if interval <= 0:
        return

    send_keyframe = getattr(video_sender, "_send_keyframe", None)
    if not callable(send_keyframe):
        logger.warning("Periodic keyframe refresh is unavailable in this aiortc version")
        return

    try:
        while True:
            await asyncio.sleep(interval)
            send_keyframe()
            logger.debug(f"Requested video keyframe for sessionid={sessionid}")
    except asyncio.CancelledError:
        logger.debug(f"Periodic keyframe refresh stopped for sessionid={sessionid}")


def ensure_models_and_avatars():
    """确保静态数字人资源存在；静态模式不再下载或加载唇形模型。"""
    data_dir = os.path.join(pwd_path, "data")
    models_dir = os.path.join(pwd_path, "models")
    
    # 创建必要的目录
    os.makedirs(data_dir, exist_ok=True)
    os.makedirs(models_dir, exist_ok=True)
    
    logger.info("=== 检查模型和形象文件 ===")
    
    # 获取下载配置
    avatar_config = get_avatar_download_config()
    # 检查并下载形象文件
    for avatar_name, config in avatar_config.items():
        # 源码运行时是项目根目录，PyInstaller 运行时是 _internal 资源目录。
        # 不能使用当前工作目录，否则双击 EXE 时会误判内置头像不存在并联网下载。
        avatar_dir = os.path.join(data_dir, avatar_name)
        if not os.path.exists(avatar_dir):
            logger.info(f"形象文件 {avatar_name} ({config['size']}) 不存在，开始下载...")
            logger.info(f"描述: {config['description']}")
            try:
                # 下载并自动解压
                archive_path = config["path"]
                if not os.path.isabs(archive_path):
                    archive_path = os.path.join(data_dir, os.path.basename(archive_path))
                http_get(config["url"], archive_path, extract=True)
                logger.info(f"✓ 形象文件 {avatar_name} 下载并解压完成")
                
                # 清理zip文件
                if os.path.exists(archive_path):
                    os.remove(archive_path)
                    logger.info(f"已清理临时文件 {archive_path}")
                    
            except Exception as e:
                logger.error(f"✗ 下载形象文件 {avatar_name} 失败: {e}")
                logger.error("请尝试手动下载或检查网络连接")
                raise
        else:
            logger.info(f"✓ 形象文件 {avatar_name} 已存在")
    
    logger.info("=== 所有文件检查完成 ===")


def build_nerfreal(sessionid: int) -> BaseReal:
    opt.sessionid = sessionid
    from src.staticreal import StaticAvatarReal
    return StaticAvatarReal(opt, avatar)


async def _offer_impl(request):
    params = await request.json()
    offer = RTCSessionDescription(sdp=params["sdp"], type=params["type"])
    
    # 获取avatar_id参数，如果没有则使用默认
    avatar_id = params.get("avatar_id", opt.avatar_id)
    logger.info(f'Requested avatar_id: {avatar_id}')
    
    # 根据avatar_id加载对应的配置
    avatar_config = get_avatar_config(avatar_id)
    if avatar_config:
        logger.info(f'Using avatar: {avatar_config["name"]} ({avatar_config["description"]})')
        # 临时修改opt以使用指定的avatar配置
        temp_opt = argparse.Namespace(**vars(opt))
        temp_opt.avatar_id = avatar_config["avatar_dir"]
        temp_opt.REF_FILE = avatar_config["tts_config"]["voice"]
        temp_opt.tts = avatar_config["tts_config"]["type"]
    else:
        temp_opt = opt
        logger.warning(f'Avatar config not found for {avatar_id}, using default')

    sessionid = uuid.uuid4().int % 1000000
    nerfreals[sessionid] = None
    logger.debug(f"sessionid={sessionid}, session num={len(nerfreals)}")
    
    # 静态头像模式不加载 Wav2Lip 权重，嘴部始终保持初始帧状态。
    temp_opt.sessionid = sessionid
    from src.staticreal import StaticAvatarReal
    if temp_opt.gpu_server_url:
        logger.warning("静态头像模式已启用，忽略 --gpu_server_url")
    
    # 为这个会话加载对应的avatar
    if temp_opt.avatar_id != opt.avatar_id:
        # 需要加载不同的avatar
        from src.avatar import load_avatar
        session_avatar = load_avatar(temp_opt.avatar_id)
    else:
        session_avatar = avatar
    
    nerfreal = StaticAvatarReal(temp_opt, session_avatar)
    nerfreals[sessionid] = nerfreal
    pc = RTCPeerConnection(configuration=RTCConfiguration(
        iceServers=[],
    ))
    pcs.add(pc)
    keyframe_task = None

    @pc.on("connectionstatechange")
    async def on_connectionstatechange():
        logger.info(f"Connection state is {pc.connectionState}  sessionid={sessionid}")
        nerfreal = nerfreals.get(sessionid)
        if pc.connectionState == "failed":
            if nerfreal is not None:
                nerfreal.stop_client_voice()
            if keyframe_task:
                keyframe_task.cancel()
            await pc.close()
            pcs.discard(pc)
            if sessionid in nerfreals:
                del nerfreals[sessionid]
        if pc.connectionState == "closed":
            if nerfreal is not None:
                nerfreal.stop_client_voice()
            if keyframe_task:
                keyframe_task.cancel()
            pcs.discard(pc)
            if sessionid in nerfreals:
                del nerfreals[sessionid]
    
    @pc.on("datachannel")
    def on_datachannel(channel):
        logger.info(f"Data channel established: {channel.label}")
        # 将数据通道传递给player，以便发送LLM回答
        player.set_data_channel(channel)

        @channel.on("message")
        def on_message(message):
            logger.debug(f"Received message from client: {message}")
            try:
                payload = json.loads(message)
                message_type = payload.get('type')
                if message_type == 'voice_start':
                    ok, error = nerfreals[sessionid].start_client_voice()
                    if not ok:
                        nerfreals[sessionid].send_data_channel_message({
                            'type': 'voice_error',
                            'message': error,
                        })
                elif message_type == 'voice_stop':
                    nerfreals[sessionid].stop_client_voice()
            except (TypeError, ValueError, json.JSONDecodeError):
                logger.debug("Ignoring non-control data channel message")

    @pc.on("track")
    def on_track(track):
        logger.info(f"Received track: {track.kind}")
        if track.kind == "audio":
            # 客户端发送了音频轨道，用于语音识别
            logger.info("Client audio track received for ASR")
            # 将音频轨道传递给 nerfreal 进行 ASR 处理
            nerfreals[sessionid].set_client_audio_track(track)

    player = HumanPlayer(nerfreals[sessionid])
    audio_sender = pc.addTrack(player.audio)
    video_sender = pc.addTrack(player.video)
    keyframe_interval = float(getattr(temp_opt, "keyframe_interval", 0.0) or 0.0)
    if keyframe_interval > 0:
        keyframe_task = asyncio.create_task(
            force_periodic_keyframes(video_sender, sessionid, keyframe_interval)
        )
    capabilities = RTCRtpSender.getCapabilities("video")
    preferences = list(filter(lambda x: x.name == "H264", capabilities.codecs))
    preferences += list(filter(lambda x: x.name == "VP8", capabilities.codecs))
    preferences += list(filter(lambda x: x.name == "rtx", capabilities.codecs))
    transceiver = pc.getTransceivers()[1]
    transceiver.setCodecPreferences(preferences)

    await pc.setRemoteDescription(offer)

    answer = await pc.createAnswer()
    video_bitrate = int(getattr(temp_opt, "video_bitrate", 0) or 0)
    if video_bitrate > 0:
        answer = RTCSessionDescription(
            sdp=set_video_bitrate(answer.sdp, video_bitrate),
            type=answer.type,
        )
        logger.info(f"Applied video bitrate hint: {video_bitrate} kbps")
    await pc.setLocalDescription(answer)
    return web.Response(
        content_type="application/json",
        text=json.dumps(
            {"sdp": pc.localDescription.sdp, "type": pc.localDescription.type, "sessionid": sessionid}
        ),
    )


async def offer(request):
    """处理 WebRTC 协商并把后端异常转换为可诊断的 JSON 响应。"""
    previous_sessions = set(nerfreals)
    previous_pcs = set(pcs)
    try:
        return await _offer_impl(request)
    except Exception as exc:
        logger.exception("WebRTC /offer 处理失败")
        # 协商中途失败时清理新建会话，避免重复重试后占满 max_session。
        for sessionid in set(nerfreals) - previous_sessions:
            nerfreal = nerfreals.pop(sessionid, None)
            if nerfreal is not None:
                nerfreal.stop_client_voice()
        for pc in set(pcs) - previous_pcs:
            try:
                await pc.close()
            finally:
                pcs.discard(pc)
        return web.json_response(
            {
                "code": -1,
                "msg": f"WebRTC 协商失败: {exc}",
                "error_type": type(exc).__name__,
            },
            status=500,
        )


async def human(request):
    try:
        params = await request.json()

        sessionid = params.get('sessionid', 0)
        if sessionid not in nerfreals or nerfreals[sessionid] is None:
            return web.Response(
                content_type="application/json",
                text=json.dumps(
                    {"code": -1, "msg": f"invalid sessionid: {sessionid}"}
                ),
            )

        if params.get('interrupt'):
            nerfreals[sessionid].flush_talk()

        if params['type'] == 'echo':
            nerfreals[sessionid].put_msg_txt(params['text'])
        elif params['type'] == 'chat':
            asyncio.get_event_loop().run_in_executor(
                None,
                llm_response,
                params['text'],
                nerfreals[sessionid],
                sessionid,
            )

        return web.Response(
            content_type="application/json",
            text=json.dumps(
                {"code": 0, "msg": "ok"}
            ),
        )
    except Exception as e:
        logger.exception('exception:')
        return web.Response(
            content_type="application/json",
            text=json.dumps(
                {"code": -1, "msg": str(e)}
            ),
        )


async def interrupt_talk(request):
    try:
        params = await request.json()

        sessionid = params.get('sessionid', 0)
        nerfreals[sessionid].flush_talk()

        return web.Response(
            content_type="application/json",
            text=json.dumps(
                {"code": 0, "msg": "ok"}
            ),
        )
    except Exception as e:
        logger.exception('exception:')
        return web.Response(
            content_type="application/json",
            text=json.dumps(
                {"code": -1, "msg": str(e)}
            ),
        )


async def voice_start(request):
    """为当前 WebRTC 会话启动 DashScope 实时语音识别。"""
    try:
        params = await request.json()
        sessionid = params.get('sessionid', 0)
        nerfreal = nerfreals.get(sessionid)
        if nerfreal is None:
            return web.json_response({'code': -1, 'msg': f'invalid sessionid: {sessionid}'})

        ok, error = nerfreal.start_client_voice()
        if not ok:
            return web.json_response({'code': -1, 'msg': error})
        return web.json_response({'code': 0, 'msg': 'ok'})
    except Exception as exc:
        logger.exception('voice_start exception:')
        return web.json_response({'code': -1, 'msg': str(exc)})


async def voice_stop(request):
    """停止当前 WebRTC 会话的实时语音识别。"""
    try:
        params = await request.json()
        sessionid = params.get('sessionid', 0)
        nerfreal = nerfreals.get(sessionid)
        if nerfreal is None:
            return web.json_response({'code': -1, 'msg': f'invalid sessionid: {sessionid}'})

        nerfreal.stop_client_voice()
        return web.json_response({'code': 0, 'msg': 'ok'})
    except Exception as exc:
        logger.exception('voice_stop exception:')
        return web.json_response({'code': -1, 'msg': str(exc)})


async def humanaudio(request):
    try:
        form = await request.post()
        sessionid = int(form.get('sessionid', 0))
        fileobj = form["file"]
        filename = fileobj.filename
        filebytes = fileobj.file.read()
        nerfreals[sessionid].put_audio_file(filebytes)

        return web.Response(
            content_type="application/json",
            text=json.dumps(
                {"code": 0, "msg": "ok"}
            ),
        )
    except Exception as e:
        logger.exception('exception:')
        return web.Response(
            content_type="application/json",
            text=json.dumps(
                {"code": -1, "msg": str(e)}
            ),
        )


async def set_audiotype(request):
    try:
        params = await request.json()

        sessionid = params.get('sessionid', 0)
        nerfreals[sessionid].set_custom_state(params['audiotype'], params['reinit'])

        return web.Response(
            content_type="application/json",
            text=json.dumps(
                {"code": 0, "msg": "ok"}
            ),
        )
    except Exception as e:
        logger.exception('exception:')
        return web.Response(
            content_type="application/json",
            text=json.dumps(
                {"code": -1, "msg": str(e)}
            ),
        )


async def record(request):
    try:
        params = await request.json()

        sessionid = params.get('sessionid', 0)
        if params['type'] == 'start_record':
            # nerfreals[sessionid].put_msg_txt(params['text'])
            nerfreals[sessionid].start_recording()
        elif params['type'] == 'end_record':
            nerfreals[sessionid].stop_recording()
        return web.Response(
            content_type="application/json",
            text=json.dumps(
                {"code": 0, "msg": "ok"}
            ),
        )
    except Exception as e:
        logger.exception('exception:')
        return web.Response(
            content_type="application/json",
            text=json.dumps(
                {"code": -1, "msg": str(e)}
            ),
        )


async def is_speaking(request):
    params = await request.json()

    sessionid = params.get('sessionid', 0)
    return web.Response(
        content_type="application/json",
        text=json.dumps(
            {"code": 0, "data": nerfreals[sessionid].is_speaking()}
        ),
    )


async def get_avatars(request):
    """获取所有可用的数字人列表"""
    try:
        config = get_avatars_config()
        return web.Response(
            content_type="application/json",
            text=json.dumps(
                {"code": 0, "data": config["avatars"]}
            ),
        )
    except Exception as e:
        logger.exception('get_avatars exception:')
        return web.Response(
            content_type="application/json",
            text=json.dumps(
                {"code": -1, "msg": str(e)}
            ),
        )


async def get_system_prompt_api(request):
    """返回当前持久化的系统提示词。"""
    return web.json_response({"code": 0, "data": {"system_prompt": get_system_prompt()}})


async def update_system_prompt_api(request):
    """保存桌面端设置页提交的系统提示词。"""
    try:
        params = await request.json()
        prompt = set_system_prompt(params.get("system_prompt", ""))
        return web.json_response({"code": 0, "msg": "ok", "data": {"system_prompt": prompt}})
    except (ValueError, TypeError) as exc:
        return web.json_response({"code": 400, "msg": str(exc)}, status=400)
    except Exception as exc:
        logger.exception("update_system_prompt exception:")
        return web.json_response({"code": 500, "msg": str(exc)}, status=500)


async def get_logs_api(request):
    """返回最近的服务日志，供桌面版调试窗口实时查看。"""
    try:
        requested_lines = int(request.query.get('lines', '300'))
    except (TypeError, ValueError):
        requested_lines = 300
    line_count = max(20, min(requested_lines, 1000))
    log_path = get_log_file_path()
    launcher_log_path = log_path.with_name('launcher.log')
    lines = []
    files = []
    for current_path, label in ((launcher_log_path, '启动器日志'), (log_path, '服务日志')):
        try:
            current_lines = current_path.read_text(encoding='utf-8', errors='replace').splitlines()
        except OSError:
            current_lines = []
        if current_lines:
            lines.extend([f'===== {label}: {current_path} =====', *current_lines])
            files.append(str(current_path))
    if not files:
        return web.json_response(
            {'code': -1, 'msg': '日志文件尚未生成', 'data': {'lines': [], 'files': []}},
            status=404,
        )
    return web.json_response({
        'code': 0,
        'data': {'path': str(log_path), 'files': files, 'lines': lines[-line_count:]},
    })


async def on_shutdown(app):
    for nerfreal in list(nerfreals.values()):
        if nerfreal is not None:
            nerfreal.stop_client_voice()
    # close peer connections
    coros = [pc.close() for pc in pcs]
    await asyncio.gather(*coros)
    pcs.clear()


async def post(url, data):
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, data=data) as response:
                return await response.text()
    except aiohttp.ClientError as e:
        logger.info(f'Error: {e}')


def main(argv=None):
    """解析启动参数并启动 aiohttp/WebRTC 服务。"""
    global opt, model, avatar
    parser = argparse.ArgumentParser()

    # audio FPS
    parser.add_argument('--fps', type=int, default=50, help="audio fps,must be 50")
    # sliding window left-middle-right length (unit: 20ms)
    parser.add_argument('-l', type=int, default=10)
    parser.add_argument('-m', type=int, default=8)
    parser.add_argument('-r', type=int, default=10)

    parser.add_argument('--W', type=int, default=450, help="GUI width")
    parser.add_argument('--H', type=int, default=450, help="GUI height")
    parser.add_argument('--sharpen_strength', type=float, default=0.12,
                        help="frame sharpening strength, 0 disables")
    parser.add_argument('--video_bitrate', type=int, default=8000,
                        help="video bandwidth hint in kbps, 0 disables")
    parser.add_argument('--keyframe_interval', type=float, default=5.0,
                        help="seconds between video keyframe refreshes, 0 disables")
    parser.add_argument('--preload_enhanced_frames', type=int, default=1,
                        help="pre-enhance avatar frames in RAM, 1 enables, 0 disables")

    # musetalk opt
    parser.add_argument('--avatar_id', type=str, default='wav2lip_avatar_wzj2cjl', help="define which avatar in data directory")
    parser.add_argument('--batch_size', type=int, default=64, help="infer batch")
    parser.add_argument('--customvideo_config', type=str, default='', help="custom action json")

    parser.add_argument('--tts', type=str, default='dashscope',
                        help="TTS service type; dashscope uses Qwen-TTS and only needs DASHSCOPE_API_KEY")
    parser.add_argument('--REF_FILE', type=str, default="libai_v2",
                        help="DashScope voice name, default is the CosyVoice Li Bai voice libai_v2")
    parser.add_argument('--REF_TEXT', type=str, default=None)
    parser.add_argument('--TTS_SERVER', type=str, default='')  # http://localhost:9000

    # GPU服务器配置（用于wav2lip远程推理）
    parser.add_argument('--gpu_server_url', type=str, default='',
                        help='Remote GPU server URL for wav2lip, e.g., http://29.245.58.12:8080')

    parser.add_argument('--max_session', type=int, default=1)  # multi session count
    parser.add_argument('--port', type=int, default=8010, help="web listen port")

    opt = parser.parse_args(argv)
    opt.customopt = []
    if opt.customvideo_config != '':
        with open(opt.customvideo_config, 'r') as file:
            opt.customopt = json.load(file)
    
    # 确保模型和形象文件存在
    logger.info("检查并下载必要的模型和形象文件...")
    ensure_models_and_avatars()
    
    from src.avatar import load_avatar, preload_avatars

    logger.info("Static avatar mode enabled; Wav2Lip model loading is disabled")
    model = None
    avatar = load_avatar(opt.avatar_id)
    
    # 预加载所有配置的avatars
    logger.info("预加载所有数字人形象到内存...")
    avatars_config = get_avatars_config()
    avatar_ids_to_preload = [a['avatar_dir'] for a in avatars_config['avatars']]
    preload_avatars(avatar_ids_to_preload)
    if int(getattr(opt, 'preload_enhanced_frames', 1) or 0):
        logger.info("预热默认数字人增强帧缓存...")
        prepare_enhanced_frame_cache_for_frames(
            avatar[0],
            opt.avatar_id,
            getattr(opt, 'sharpen_strength', 0.0),
            True,
        )

    # app async
    appasync = web.Application(client_max_size=1024 ** 2 * 100)
    appasync.on_shutdown.append(on_shutdown)
    appasync.router.add_post("/offer", offer)
    appasync.router.add_post("/human", human)
    appasync.router.add_post("/voice/start", voice_start)
    appasync.router.add_post("/voice/stop", voice_stop)
    appasync.router.add_post("/humanaudio", humanaudio)
    appasync.router.add_post("/set_audiotype", set_audiotype)
    appasync.router.add_post("/record", record)
    appasync.router.add_post("/interrupt_talk", interrupt_talk)
    appasync.router.add_post("/is_speaking", is_speaking)
    appasync.router.add_get("/api/avatars", get_avatars)
    appasync.router.add_get("/api/settings/system-prompt", get_system_prompt_api)
    appasync.router.add_put("/api/settings/system-prompt", update_system_prompt_api)
    appasync.router.add_get("/api/logs", get_logs_api)
    # 所有静态资源都从程序资源根目录解析，不能依赖启动进程的当前工作目录。
    # 双击 EXE、快捷方式启动或从其它目录调用时，cwd 可能是 E:\\1 等任意路径。
    data_static_path = os.path.join(pwd_path, 'data')
    static_path = os.path.join(pwd_path, 'static')
    appasync.router.add_static('/data', path=data_static_path)  # 添加头像资源访问
    appasync.router.add_static('/', path=static_path)

    # Configure default CORS settings.
    cors = aiohttp_cors.setup(appasync, defaults={
        "*": aiohttp_cors.ResourceOptions(
            allow_credentials=True,
            expose_headers="*",
            allow_headers="*",
        )
    })
    # Configure CORS on all routes.
    for route in list(appasync.router.routes()):
        cors.add(route)

    logger.info('如果使用webrtc，推荐访问webrtc集成前端: http://127.0.0.1:' + str(opt.port) + '/index.html')

    runner = web.AppRunner(appasync)
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(runner.setup())
    site = web.TCPSite(runner, '127.0.0.1', opt.port)
    loop.run_until_complete(site.start())
    loop.run_forever()


if __name__ == '__main__':
    main()

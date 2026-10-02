/**
 * AI Avatar WebRTC 客户端 - Talk 页面版本
 */

// 浏览器控制台在桌面内置窗口中不可见，保留最近的客户端诊断信息供日志窗口读取。
window.alibaiClientLogs = window.alibaiClientLogs || [];
function recordClientLog(message, error) {
    const detail = error && error.stack ? `\n${error.stack}` : (error ? `\n${error}` : '');
    window.alibaiClientLogs.push(`[浏览器] ${new Date().toLocaleTimeString()} ${message}${detail}`);
    if (window.alibaiClientLogs.length > 100) window.alibaiClientLogs.shift();
}

class AvatarClient {
    constructor() {
        // WebRTC 相关
        this.pc = null;
        this.dataChannel = null;
        this.remoteStream = new MediaStream();
        this.localStream = null;  // 本地麦克风流
        this.recognition = null;
        this.voiceControlRequest = null;
        this.voiceInputStartCancelled = false;

        // 状态管理
        this.isConnected = false;
        this.isStarted = false;
        this.isRecording = false;
        this.isSpeaking = false;
        this.voiceSilenceTimer = null;
        this.remoteVideoWasMuted = false;
        this.sessionid = 0;
        this.subtitleEnabled = true;  // 字幕开关状态
        this.subtitleTimer = null;  // 字幕隐藏定时器
        this.currentSubtitle = '';  // 当前显示的字幕文本
        
        // DOM 元素
        this.remoteVideo = document.getElementById('remoteVideo');
        this.loadingOverlay = document.getElementById('loadingOverlay');
        this.subtitleOverlay = document.getElementById('subtitleOverlay');
        
        // 获取URL参数
        this.avatarId = 'ai_libai';
        this.avatarName = '以太李白';  // 默认名称，稍后从配置获取
        this.avatarImage = '';  // avatar图片路径
        
        // 初始化
        this.init();
    }

    async init() {
        try {
            // 从API获取avatar配置
            await this.loadAvatarConfig();
            
            // 设置页面标题
            document.title = `${this.avatarName}`;
            
            // 进入页面时只显示开始按钮
            this.hideControlButtons();
            this.updateLoadingProgress('点击开始对话，开启声音和视频');
            
        } catch (error) {
            console.error('初始化失败:', error);
            recordClientLog('初始化失败', error);
            this.showError('初始化失败，请刷新页面重试');
        }
    }

    getUrlParam(name) {
        const urlParams = new URLSearchParams(window.location.search);
        return urlParams.get(name);
    }

    async loadAvatarConfig() {
        try {
            // 从API获取avatar配置
            const response = await fetch('/api/avatars');
            const result = await response.json();
            
            if (result.code === 0 && result.data) {
                const avatarConfig = result.data.find(a => a.id === this.avatarId);
                if (avatarConfig) {
                    this.avatarName = avatarConfig.name;
                    this.avatarImage = avatarConfig.image;
                    console.log(`Avatar配置加载成功: ${this.avatarName}, 图片: ${this.avatarImage}`);
                    
                    // 设置加载背景图和图标
                    this.setLoadingBackground();
                } else {
                    console.warn(`未找到avatar配置: ${this.avatarId}`);
                }
            }
        } catch (error) {
            console.error('加载avatar配置失败:', error);
        }
    }

    setLoadingBackground() {
        if (this.avatarImage) {
            // 设置加载遮罩的背景图（使用独立的背景层）
            const loadingBg = document.getElementById('loadingBackground');
            if (loadingBg) {
                loadingBg.style.backgroundImage = `url(${this.avatarImage})`;
            }
            
            // 设置加载图标为avatar头像
            const loadingIcon = document.getElementById('loadingIcon');
            if (loadingIcon) {
                loadingIcon.innerHTML = `<img src="${this.avatarImage}" alt="${this.avatarName}">`;
            }
        }
    }

    updateLoadingProgress(text, buttonText = null) {
        const progressEl = document.getElementById('loadingProgress');
        if (progressEl) {
            progressEl.textContent = text;
        }
        if (buttonText) {
            this.setStartButtonBusy(buttonText);
        }
    }

    setStartButtonBusy(text) {
        const startBtn = document.getElementById('startChatBtn');
        if (startBtn && startBtn.disabled) {
            startBtn.innerHTML = `<i class="bi bi-hourglass-split"></i> ${text}`;
        }
    }

    async startConversation() {
        if (this.isStarted) return;
        this.isStarted = true;
        try {
            await this.ensureRemotePlayback();
            this.updateLoadingProgress('正在唤醒以太李白...', '正在唤醒');
            
            // 连接WebRTC
            await this.connect();
            
            // 设置语音识别和按住说话
            this.setupSpeechRecognition();
            this.setupPushToTalk();
        } catch (error) {
            this.isStarted = false;
            this.resetStartButton();
            throw error;
        }
    }

    async connect() {
        try {
            // 立即开始negotiate，减少延迟
            // 创建 RTCPeerConnection
            this.pc = new RTCPeerConnection({
                sdpSemantics: 'unified-plan',
                iceServers: []
            });

            // 监听远程音视频流
            this.pc.addEventListener('track', (event) => {
                console.log('收到远程媒体流:', event.track.kind);
                if (event.streams && event.streams[0]) {
                    if (this.remoteVideo.srcObject !== event.streams[0]) {
                        this.remoteVideo.srcObject = event.streams[0];
                    }
                } else {
                    this.remoteStream.addTrack(event.track);
                    this.remoteVideo.srcObject = this.remoteStream;
                }

                this.ensureRemotePlayback();

                if (event.track.kind === 'video') {
                    this.hideLoading();
                    this.hideStartButton();
                    // 接通后显示所有控制按钮
                    this.showControlButtons();
                }
            });

            // ICE候选处理
            this.pc.onicecandidate = (event) => {
                if (event.candidate) {
                    console.log('ICE候选:', event.candidate);
                }
            };

            // 连接状态监听
            this.pc.onconnectionstatechange = () => {
                console.log('连接状态:', this.pc.connectionState);
                if (this.pc.connectionState === 'connected') {
                    this.isConnected = true;
                    this.hideLoading();
                    this.hideStartButton();
                    // 接通后显示所有控制按钮
                    this.showControlButtons();
                } else if (this.pc.connectionState === 'failed') {
                    this.isStarted = false;
                    this.resetStartButton();
                    this.showError('连接失败，请刷新页面重试');
                }
            };

            // 创建数据通道
            this.dataChannel = this.pc.createDataChannel('chat');
            this.setupDataChannel();

            // 获取麦克风权限并添加音频轨道用于语音识别
            try {
                this.localStream = await navigator.mediaDevices.getUserMedia({
                    audio: {
                        echoCancellation: true,
                        noiseSuppression: true,
                        autoGainControl: true
                    }
                });
                console.log('麦克风权限已获取');

                // 添加音频轨道到 PeerConnection，direction 设为 sendonly
                this.localStream.getAudioTracks().forEach(track => {
                    // 连接建立后默认不发送麦克风，只有用户启动语音输入时才启用。
                    track.enabled = false;
                    this.pc.addTrack(track, this.localStream);
                });
            } catch (error) {
                console.error('获取麦克风权限失败:', error);
                this.showError('无法访问麦克风，语音输入功能将不可用。请在浏览器设置中允许麦克风访问。');
                // 继续连接，只是没有语音输入功能
            }

            // 参考 client.js 的 negotiate 方法
            await this.negotiate();

            console.log('WebRTC连接成功');

        } catch (error) {
            console.error('连接失败:', error);
            recordClientLog('WebRTC 连接失败', error);
            this.showError('连接失败: ' + error.message);
            throw error;
        }
    }

    async waitForIceGatheringComplete(timeoutMs = 2000) {
        const pc = this.pc;
        if (!pc || pc.iceGatheringState === 'complete') return;

        await new Promise((resolve) => {
            let finished = false;
            const finish = () => {
                if (finished) return;
                finished = true;
                clearTimeout(timer);
                pc.removeEventListener('icegatheringstatechange', checkState);
                resolve();
            };
            const checkState = () => {
                if (pc.iceGatheringState === 'complete') {
                    finish();
                }
            };
            const timer = setTimeout(() => {
                console.warn(`ICE收集超过${timeoutMs}ms，继续发送offer`);
                finish();
            }, timeoutMs);

            pc.addEventListener('icegatheringstatechange', checkState);
            checkState();
        });
    }

    async negotiate() {
        try {
            // 添加进度提示
            this.updateLoadingProgress('正在建立连接...', '建立连接');
            
            // 添加 transceiver - 参考 client.js
            this.pc.addTransceiver('video', { direction: 'recvonly' });
            this.pc.addTransceiver('audio', { direction: 'recvonly' });

            // 创建 offer
            const offer = await this.pc.createOffer();
            await this.pc.setLocalDescription(offer);

            this.updateLoadingProgress('正在收集信息...', '收集信息');
            
            // ICE gathering can stall in some browsers; keep the call flow moving.
            await this.waitForIceGatheringComplete(2000);

            this.updateLoadingProgress('正在加载以太李白...', '请求服务');
            
            // 记录开始时间
            const startTime = Date.now();
            
            // 发送 offer 到服务器
            const response = await this.postOffer({
                sdp: this.pc.localDescription.sdp,
                type: this.pc.localDescription.type,
                avatar_id: this.avatarId
            });

            if (!response.ok) {
                const errorText = await response.text();
                let errorMessage = errorText || response.statusText;
                try {
                    const errorData = JSON.parse(errorText);
                    errorMessage = errorData.msg || errorMessage;
                } catch (_) {
                    // 非 JSON 响应保留原始正文，便于诊断代理层或框架错误。
                }
                throw new Error(`/offer ${response.status}: ${errorMessage}`);
            }

            const answer = await response.json();
            if (!answer || !answer.sdp || !answer.type) {
                throw new Error('服务器没有返回有效的WebRTC answer');
            }
            
            // 记录耗时
            const elapsedTime = Date.now() - startTime;
            console.log(`Offer请求耗时: ${elapsedTime}ms`);
            
            if (elapsedTime > 3000) {
                console.warn('Offer请求耗时过长，可能是因为后端需要加载avatar模型');
            }
            
            this.updateLoadingProgress('正在建立视频连接...', '接入视频');
            
            // 保存sessionid
            this.sessionid = answer.sessionid;
            console.log('Session ID:', this.sessionid);
            
            // 设置远程描述
            await this.pc.setRemoteDescription(answer);
            
            this.updateLoadingProgress('等待视频流...', '等待视频');
        } catch (error) {
            console.error('Negotiate失败:', error);
            recordClientLog('WebRTC 协商失败', error);
            this.updateLoadingProgress('连接失败');
            throw error;
        }
    }

    async postOffer(payload, timeoutMs = 60000) {
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), timeoutMs);
        try {
            return await fetch('/offer', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(payload),
                signal: controller.signal
            });
        } catch (error) {
            if (error.name === 'AbortError') {
                throw new Error(`/offer 超过${Math.round(timeoutMs / 1000)}秒没有返回，后端可能卡在模型加载或推理初始化`);
            }
            throw error;
        } finally {
            clearTimeout(timeoutId);
        }
    }

    setupDataChannel() {
        this.dataChannel.onopen = () => {
            console.log('数据通道已打开');
        };

        this.dataChannel.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);
                this.handleDataChannelMessage(data);
            } catch (error) {
                console.error('处理消息失败:', error);
            }
        };

        this.dataChannel.onerror = (error) => {
            console.error('数据通道错误:', error);
        };

        this.dataChannel.onclose = () => {
            console.log('数据通道已关闭');
            this.isConnected = false;
        };
    }

    async ensureRemotePlayback() {
        if (!this.remoteVideo) return;
        this.remoteVideo.muted = false;
        this.remoteVideo.volume = 1.0;
        if (!this.remoteVideo.srcObject && !this.remoteVideo.currentSrc) {
            return;
        }
        try {
            const playPromise = this.remoteVideo.play();
            if (playPromise && typeof playPromise.then === 'function') {
                await Promise.race([
                    playPromise,
                    new Promise(resolve => setTimeout(resolve, 1000))
                ]);
            }
        } catch (error) {
            console.warn('浏览器暂时阻止自动播放音频，等待用户交互后恢复播放:', error);
        }
    }

    handleDataChannelMessage(data) {
        console.log('收到数据通道消息:', data);

        switch (data.type) {
            case 'asr':
                // 语音识别结果
                console.log('ASR结果:', data.text);
                this.showSubtitle(data.text);
                // 添加到聊天窗口
                this.addChatMessage('user', data.text);
                break;

            case 'voice_error':
                console.error('后端语音识别错误:', data.message);
                if (this.isRecording) {
                    this.isRecording = false;
                    if (this.localStream) {
                        this.localStream.getAudioTracks().forEach(track => {
                            track.enabled = false;
                        });
                    }
                    this.updateVoiceInputUi(false);
                    this.restoreRemoteAudio();
                }
                this.showError(`语音识别失败：${data.message}`);
                break;

            case 'voice_status':
                console.log('后端语音识别状态:', data.status);
                break;
                
            case 'llm':
                // AI回复 - 显示在字幕和聊天窗口
                console.log('LLM回答:', data.text);
                // 累积字幕文本（因为LLM是流式返回，按句子分段）
                this.currentSubtitle = data.text;
                this.showSubtitle(data.text);
                // 添加到聊天窗口
                this.addChatMessage('assistant', data.text);
                
                // 清除之前的定时器
                if (this.subtitleTimer) {
                    clearTimeout(this.subtitleTimer);
                    this.subtitleTimer = null;
                }
                
                // 注意：不在这里设置隐藏定时器，等待 tts_end 事件
                break;
                
            case 'tts_start':
                // 开始说话
                this.isSpeaking = true;
                this.ensureRemotePlayback();
                console.log('数字人开始说话');
                
                // 清除任何现有的隐藏定时器
                if (this.subtitleTimer) {
                    clearTimeout(this.subtitleTimer);
                    this.subtitleTimer = null;
                }
                break;
                
            case 'tts_end':
                // 结束说话
                this.isSpeaking = false;
                console.log('数字人结束说话');
                
                // 数字人说完话后，延迟3秒再隐藏字幕
                if (this.subtitleTimer) {
                    clearTimeout(this.subtitleTimer);
                }
                this.subtitleTimer = setTimeout(() => {
                    this.hideSubtitle();
                }, 3000);
                break;
                
            case 'error':
                // 错误消息
                console.error('错误:', data.message);
                this.showError(data.message);
                break;
        }
    }

    // 参考index.html的对话模式实现，使用main.py的human函数
    async sendTextMessage(text) {
        if (!text || !text.trim()) return;

        try {
            await this.ensureRemotePlayback();
            console.log('发送聊天消息:', text);
            
            // 显示在字幕上
            this.showSubtitle(text);
            
            // 添加到聊天窗口
            this.addChatMessage('user', text);
            
            // 使用/human接口，type='chat' - 参考index.html
            const response = await fetch('/human', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    text: text,
                    type: 'chat',
                    interrupt: true,
                    sessionid: this.sessionid
                })
            });

            if (!response.ok) {
                throw new Error(`/human ${response.status}: ${response.statusText}`);
            }

            const data = await response.json();
            if (data.code !== 0) {
                throw new Error(data.msg || '对话服务拒绝了本次请求');
            }
            console.log('发送成功:', data);
            
            // LLM回答会通过数据通道返回，在handleDataChannelMessage中处理

        } catch (error) {
            console.error('发送消息失败:', error);
            this.showError('发送失败，请重试');
        }
    }

    // 添加聊天消息到窗口
    addChatMessage(role, text) {
        const chatMessages = document.getElementById('chatMessages');
        if (!chatMessages) {
            console.error('chatMessages元素未找到');
            return;
        }

        const messageDiv = document.createElement('div');
        messageDiv.className = `message ${role}`;
        
        const labelDiv = document.createElement('div');
        labelDiv.className = 'message-label';
        labelDiv.textContent = role === 'user' ? '' : this.avatarName;
        
        const bubbleDiv = document.createElement('div');
        bubbleDiv.className = 'message-bubble';
        bubbleDiv.textContent = text;
        
        messageDiv.appendChild(labelDiv);
        messageDiv.appendChild(bubbleDiv);
        chatMessages.appendChild(messageDiv);
        
        // 滚动到底部
        chatMessages.scrollTop = chatMessages.scrollHeight;
        
        console.log('添加聊天消息:', role, text);
    }

    // 语音识别由后端 DashScope ASR 完成，不依赖浏览器的在线 Web Speech 服务。
    setupSpeechRecognition() {
        // 检查是否成功获取了麦克风
        if (!this.localStream) {
            console.warn('未获取麦克风权限，语音输入功能不可用');
            return;
        }

        console.log('语音识别已就绪，使用后端ASR服务');
        this.recognition = { ready: true };

    }

    // 后端ASR模式：浏览器只负责采集音频，不启动 SpeechRecognition。
    startRecognition() {
        console.log('后端ASR将在语音会话启动后接收WebRTC音频');
    }

    clearVoiceTimers() {
        // 简化的计时器清理
        if (this.voiceSilenceTimer) {
            clearTimeout(this.voiceSilenceTimer);
            this.voiceSilenceTimer = null;
        }
    }

    updateVoiceInputUi(isActive) {
        const micBtn = document.getElementById('micBtn');
        if (!micBtn) return;

        micBtn.classList.toggle('recording', isActive);
        micBtn.setAttribute('aria-pressed', String(isActive));
        const label = isActive ? '点击结束语音输入' : '点击开始语音输入';
        micBtn.title = label;
        micBtn.setAttribute('aria-label', label);
        const icon = micBtn.querySelector('i');
        if (icon) {
            icon.className = isActive ? 'bi bi-mic-fill' : 'bi bi-mic';
        }
    }

    // 参考index.html的按住说话功能（后端ASR模式）
    setupPushToTalk() {
        let touchVoiceGesture = false;

        const isInteractiveTarget = (target) => {
            return target.closest('button, input, textarea, .chat-window');
        };

        // 为整个文档添加触摸事件
        document.addEventListener('touchstart', (e) => {
            if (isInteractiveTarget(e.target)) {
                return;
            }

            touchVoiceGesture = true;
            this.startVoiceInput();
        });

        const stopTouchVoiceInput = () => {
            if (!touchVoiceGesture) {
                return;
            }

            touchVoiceGesture = false;
            if (this.isRecording) {
                this.stopVoiceInput();
            }
        };

        document.addEventListener('touchend', stopTouchVoiceInput);
        document.addEventListener('touchcancel', stopTouchVoiceInput);

        // 桌面端：使用空格键
        document.addEventListener('keydown', (e) => {
            if (e.code === 'Space' && !this.isRecording && e.target.tagName !== 'INPUT' && e.target.tagName !== 'TEXTAREA') {
                e.preventDefault();
                this.startVoiceInput();
            }
        });

        document.addEventListener('keyup', (e) => {
            if (e.code === 'Space' && this.isRecording) {
                e.preventDefault();
                this.stopVoiceInput();
            }
        });
    }

    // 切换语音输入状态（麦克风按钮）
    toggleVoiceInput() {
        if (this.isRecording) {
            this.stopVoiceInput();
        } else {
            this.startVoiceInput();
        }
    }

    async requestVoiceControl(path) {
        const response = await fetch(path, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ sessionid: this.sessionid })
        });
        let result;
        try {
            result = await response.json();
        } catch (error) {
            throw new Error(`语音服务返回了无效响应（HTTP ${response.status}）`);
        }
        if (!response.ok || !result || result.code !== 0) {
            throw new Error(result?.msg || `语音服务请求失败（HTTP ${response.status}）`);
        }
        return result;
    }

    async startVoiceInput() {
        if (!this.localStream) {
            this.showError('麦克风不可用，请刷新页面并允许麦克风权限。');
            return;
        }

        if (this.isRecording || this.voiceControlRequest) return;

        this.voiceInputStartCancelled = false;
        this.voiceControlRequest = this.requestVoiceControl('/voice/start');
        try {
            await this.voiceControlRequest;
        } catch (error) {
            console.error('启动后端语音识别失败:', error);
            this.showError(`语音识别启动失败：${error.message}`);
            return;
        } finally {
            this.voiceControlRequest = null;
        }

        if (this.voiceInputStartCancelled) {
            this.voiceInputStartCancelled = false;
            this.requestVoiceControl('/voice/stop').catch(() => {});
            return;
        }

        this.isRecording = true;
        this.remoteVideoWasMuted = this.remoteVideo ? this.remoteVideo.muted : false;

        // 静音数字人音频，避免回声
        if (this.remoteVideo) {
            this.remoteVideo.muted = true;
        }

        // 启用音频轨道，音频将通过 WebRTC 发送到后端 ASR
        this.localStream.getAudioTracks().forEach(track => {
            track.enabled = true;
        });

        this.updateVoiceInputUi(true);
        this.showSubtitle('正在聆听，请说话...');
        console.log('语音输入已开启，音频通过WebRTC发送到后端ASR');
    }

    stopVoiceInput() {
        if (!this.isRecording) {
            if (this.voiceControlRequest) {
                this.voiceInputStartCancelled = true;
            }
            return;
        }

        this.isRecording = false;
        this.clearVoiceTimers();

        // 禁用音频轨道
        if (this.localStream) {
            this.localStream.getAudioTracks().forEach(track => {
                track.enabled = false;
            });
        }

        this.updateVoiceInputUi(false);
        this.restoreRemoteAudio();
        this.showSubtitle('语音识别已结束');
        this.requestVoiceControl('/voice/stop').catch((error) => {
            console.warn('停止后端语音识别失败:', error);
        });
        console.log('语音输入已停止');
    }

    restoreRemoteAudio() {
        if (this.remoteVideo) {
            this.remoteVideo.muted = this.remoteVideoWasMuted;
        }
    }

    showSubtitle(text) {
        // 只有在字幕开启时才显示
        if (this.subtitleEnabled) {
            this.subtitleOverlay.textContent = text;
            this.subtitleOverlay.classList.add('show');
        }
    }

    hideSubtitle() {
        // 清除定时器
        if (this.subtitleTimer) {
            clearTimeout(this.subtitleTimer);
            this.subtitleTimer = null;
        }
        
        // 延迟隐藏，确保过渡动画
        setTimeout(() => {
            this.subtitleOverlay.classList.remove('show');
        }, 100);
    }

    // 切换字幕显示状态
    toggleSubtitle() {
        this.subtitleEnabled = !this.subtitleEnabled;
        console.log('字幕状态:', this.subtitleEnabled ? '开启' : '关闭');
        
        // 如果关闭字幕，立即隐藏当前显示的字幕
        if (!this.subtitleEnabled) {
            this.subtitleOverlay.classList.remove('show');
        }
    }

    // 隐藏控制按钮（calling状态）
    hideControlButtons() {
        document.getElementById('subtitleBtn').classList.add('hidden');
        document.getElementById('micBtn').classList.add('hidden');
        document.getElementById('chatToggleBtn').classList.add('hidden');
    }

    // 显示控制按钮（接通后）
    showControlButtons() {
        document.getElementById('subtitleBtn').classList.remove('hidden');
        document.getElementById('micBtn').classList.remove('hidden');
        document.getElementById('chatToggleBtn').classList.remove('hidden');
    }

    hideStartButton() {
        const startBtn = document.getElementById('startChatBtn');
        if (startBtn) {
            startBtn.style.display = 'none';
        }
    }

    resetStartButton() {
        const startBtn = document.getElementById('startChatBtn');
        if (startBtn) {
            startBtn.disabled = false;
            startBtn.style.display = 'flex';
            startBtn.innerHTML = '<i class="bi bi-play-fill"></i> 开始对话';
        }
    }

    hideLoading() {
        this.loadingOverlay.classList.add('hidden');
    }

    showError(message) {
        console.error(message);
        recordClientLog(message);
        if (typeof window.openLogWindow === 'function') window.openLogWindow();
        alert(message);
    }

    disconnect() {
        // 停止语音识别
        this.stopVoiceInput();

        // 停止本地音频流
        if (this.localStream) {
            this.localStream.getTracks().forEach(track => track.stop());
            this.localStream = null;
        }

        // 关闭数据通道
        if (this.dataChannel) {
            this.dataChannel.close();
            this.dataChannel = null;
        }

        // 关闭 PeerConnection
        if (this.pc) {
            // 延迟关闭以确保清理完成
            setTimeout(() => {
                if (this.pc) {
                    this.pc.close();
                    this.pc = null;
                }
            }, 500);
        }

        this.isConnected = false;
    }
}

// 全局实例
let avatarClient;

// 立即初始化，不等待DOMContentLoaded
(function initClient() {
    // 检查DOM是否已加载
    if (document.readyState === 'loading') {
        // DOM未加载，等待DOMContentLoaded
        document.addEventListener('DOMContentLoaded', () => {
            console.log('DOMContentLoaded - 初始化客户端');
            avatarClient = new AvatarClient();
            window.avatarClient = avatarClient;
        });
    } else {
        // DOM已加载，立即初始化
        console.log('DOM已就绪 - 立即初始化客户端');
        avatarClient = new AvatarClient();
        window.avatarClient = avatarClient;
    }
})();

// 页面关闭时断开连接
window.onunload = function(event) {
    if (avatarClient && avatarClient.pc) {
        avatarClient.pc.close();
    }
};

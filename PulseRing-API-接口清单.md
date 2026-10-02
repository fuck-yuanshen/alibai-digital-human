# PulseRing API 接口清单

来源：<https://apimock.feypower.com/docs/PulseRing-openapi.yaml>

- OpenAPI：3.0.3
- Base URL：`https://apimock.feypower.com`
- 接口数量：73 个路径，85 个操作
- 默认认证：`Authorization: Bearer <token>`；认证相关的短信、登录、刷新接口为匿名接口
- 通用响应：`{ "code": 0, "message": "ok", "data": {...} }`

## 认证 `auth`

| 方法 | 路径 | 说明 | 请求体/参数 |
|---|---|---|---|
| POST | `/auth/sms-code` | 发送短信验证码 | `SmsCodeRequest` |
| POST | `/auth/login` | 注册/登录（验证码） | `LoginRequest` |
| POST | `/auth/refresh` | Refresh Token 刷新 | `RefreshTokenRequest` |
| GET | `/auth/session` | 获取当前会话/登录态 | - |
| POST | `/auth/logout` | 退出登录 | `RefreshTokenRequest` |

## 用户 `user`

| 方法 | 路径 | 说明 | 请求体/参数 |
|---|---|---|---|
| GET | `/user/profile` | 获取个人信息 | - |
| PUT | `/user/profile` | 更新个人信息 | `UserProfileUpdateRequest` |
| POST | `/user/avatar` | 上传/修改头像 | 文件上传 |
| PUT | `/user/password` | 修改密码 | `ChangePasswordRequest` |
| DELETE | `/user/account` | 账号注销 | - |
| GET | `/user/guest-info` | 游客信息状态 | - |

## 健康 `health`

| 方法 | 路径 | 说明 | 请求体/参数 |
|---|---|---|---|
| GET | `/health/overview` | 首页健康卡片汇总（天气、运势） | `date`, `city` |
| GET | `/health/activity` | 活动数据和 24 小时趋势 | `date` |
| PUT | `/health/activity/goal` | 设置活动目标 | `ActivityGoalRequest` |
| GET | `/health/heart-rate` | 心率数据和趋势 | `date` |
| POST | `/health/heart-rate/measure` | 实时心率测量 | - |
| PUT | `/health/heart-rate/schedule` | 定时心率监测设置 | `ScheduleRequest` |
| GET | `/health/hrv` | HRV 数据和趋势 | `date` |
| POST | `/health/hrv/measure` | 实时 HRV 测量 | - |
| PUT | `/health/hrv/schedule` | 定时 HRV 监测设置 | `ScheduleRequest` |
| GET | `/health/spo2` | 血氧数据 | `date` |
| GET | `/health/sleep` | 睡眠数据、阶段和曲线 | `date` |
| PUT | `/health/sleep/goal` | 设置睡眠目标 | JSON 对象 |
| GET | `/health/stress` | 压力数据和趋势 | `date` |
| POST | `/health/stress/measure` | 实时压力测量 | - |
| PUT | `/health/stress/schedule` | 定时压力监测设置 | `ScheduleRequest` |
| GET | `/health/sports` | 运动记录列表 | `date` |
| POST | `/health/sports/start` | 开始一段运动记录 | JSON 对象 |
| GET | `/health/period` | 生理周期信息 | - |
| PUT | `/health/period` | 更新生理周期 | JSON 对象 |
| PUT | `/health/metrics/order` | 设置首页健康卡片顺序 | JSON 对象 |
| GET | `/health/history` | 历史详细数据 | 必填：`metric`, `date_from`, `date_to`；可选：`granularity` |

## 设备 `device`

| 方法 | 路径 | 说明 | 请求体/参数 |
|---|---|---|---|
| GET | `/devices` | 设备列表 | - |
| POST | `/devices/bind` | 绑定设备（蓝牙/扫码） | JSON 对象 |
| POST | `/devices/scan` | 扫描附近蓝牙设备 | JSON 对象 |
| POST | `/devices/scan-qr` | 扫码绑定 | JSON 对象 |
| GET | `/devices/{id}` | 设备详情 | 路径参数 `id` |
| PUT | `/devices/{id}` | 更新设备设置 | JSON 对象 |
| DELETE | `/devices/{id}` | 解绑设备 | 路径参数 `id` |
| POST | `/devices/{id}/shutdown` | 关机 | 路径参数 `id` |
| POST | `/devices/{id}/activate` | 充电激活开机 | 路径参数 `id` |
| POST | `/devices/{id}/factory-reset` | 恢复出厂设置 | 路径参数 `id` |
| GET | `/devices/{id}/firmware/status` | 查询固件更新状态 | 路径参数 `id` |
| POST | `/devices/{id}/firmware/upgrade` | 执行固件升级 | 路径参数 `id` |
| GET | `/devices/{id}/firmware/upgrade/progress` | 查询固件升级进度 | 路径参数 `id` |

## 商城 `mall`

| 方法 | 路径 | 说明 | 请求体/参数 |
|---|---|---|---|
| GET | `/products` | 商品列表（分类、搜索、排序） | `tab`, `category`, `keyword`, `sort`, `page`, `page_size` |
| GET | `/products/recommended` | 首页新品/精选推荐 | - |
| GET | `/products/{id}` | 商品详情 | 路径参数 `id` |
| GET | `/cart` | 购物车列表 | - |
| POST | `/cart/item` | 加入购物车 | JSON 对象 |
| PUT | `/cart/item/{id}` | 修改购物车项 | JSON 对象 |
| DELETE | `/cart/item/{id}` | 删除购物车项 | 路径参数 `id` |
| POST | `/orders` | 确认订单并创建订单 | `CreateOrderRequest` |
| GET | `/orders` | 我的订单列表 | `status`, `keyword`, `page` |
| GET | `/orders/{id}` | 订单详情 | 路径参数 `id` |
| POST | `/orders/{id}/cancel` | 取消订单 | 路径参数 `id` |
| POST | `/orders/{id}/pay` | 发起支付 | 路径参数 `id` |
| GET | `/orders/{id}/pay/status` | 查询支付状态 | 路径参数 `id` |
| GET | `/orders/{id}/tracking` | 物流跟踪 | 路径参数 `id` |
| POST | `/refunds` | 申请退款 | JSON 对象 |
| GET | `/refunds` | 退款/售后记录列表 | - |
| GET | `/refunds/{id}` | 退款详情 | 路径参数 `id` |
| GET | `/addresses` | 收货地址列表 | - |
| POST | `/addresses` | 新增收货地址 | `AddressRequest` |
| PUT | `/addresses/{id}` | 编辑收货地址 | `AddressRequest` |
| DELETE | `/addresses/{id}` | 删除收货地址 | 路径参数 `id` |
| GET | `/coupons/center` | 领券中心 | - |
| POST | `/coupons/claim/{id}` | 领取优惠券 | 路径参数 `id` |
| GET | `/coupons/mine` | 我的优惠券 | - |
| GET | `/footprints` | 商城足迹（浏览/收藏） | 必填：`type` |
| DELETE | `/footprints` | 清空足迹 | 必填：`type` |
| DELETE | `/footprints/{product_id}` | 删除单条足迹 | 路径参数 `product_id` |
| POST | `/favorites/{productId}` | 收藏商品 | 路径参数 `productId` |
| DELETE | `/favorites/{productId}` | 取消收藏 | 路径参数 `productId` |

## AI `ai`

| 方法 | 路径 | 说明 | 请求体/参数 |
|---|---|---|---|
| POST | `/ai/fortune` | 今日运势查询 | JSON 对象 |
| POST | `/ai/outfit` | 今日穿搭 AI 推荐 | JSON 对象 |
| POST | `/ai/tarot/reading` | 塔罗答疑（抽牌和解读） | JSON 对象 |
| GET | `/weather` | 天气信息 | `city`, `latitude`, `longitude` |

## 系统 `system`

| 方法 | 路径 | 说明 | 请求体/参数 |
|---|---|---|---|
| GET | `/faqs` | 常见问题列表 | - |
| POST | `/feedback` | 提交问题反馈 | JSON 对象 |
| GET | `/system/version` | 版本信息/检查更新 | - |
| GET | `/system/qrcode` | 生成 APP 下载二维码 | - |
| GET | `/banners` | 首页 Banner | - |
| GET | `/settings` | 获取应用设置 | - |
| PUT | `/settings` | 保存应用设置 | JSON 对象 |

## 主要请求模型字段

- `SmsCodeRequest`：`phone`、`scene`
- `LoginRequest`：`phone`、`code`
- `RefreshTokenRequest`：`refresh_token`
- `UserProfileUpdateRequest`：`nickname`、`gender`、`birthday`、`height`
- `ChangePasswordRequest`：`old_password`、`new_password`
- `ActivityGoalRequest`：`steps`、`distance_km`、`calories`
- `ScheduleRequest`：`enabled`、`interval_min`
- `CreateOrderRequest`：`items`、`address_id`、`coupon_id`、`remark`
- `AddressRequest`：`name`、`phone`、`province`、`city`、`district`、`detail`、`is_default`


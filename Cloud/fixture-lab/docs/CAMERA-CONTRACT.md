# 摄像机接口边界

当前实际实现的是 **合成 RTSP 适配器**。输入端包含受控的采集时间水印，Decoder 从画面还原它；正式设备适配器尚未实现。

## 本轮实际字段

`Observation`：frame_id、device_id、channel_id、captured_at、received_at、revision、source_type、relation、reason、bbox、marker_ids。

- `device_id` 为 cam-a / cam-b；`channel_id` 暂为 main。
- `source_type` 固定 fixture，不标记为 live。
- `captured_at` 是合成源生成当前图像的时间，视频停在同一帧时不变；`received_at` 是解码后端收帧时间。
- `revision` 绑定处理时的规则版本；规则修改设置新的 not_before，修改之前采集的图像不能确认当前状态。
- 保存的图像没有 UI 的 ROI 覆盖层；坐标归一化到 0—1，UI 圈选与检测使用相同基准。

命令结果：accepted / completed / failed / unsupported / timed_out。completed 必须关联请求之后、期限之内采集的 frame_id；accepted 不是业务成功。

## 模拟模式

| 模式 | 提供画面 | 主动新图请求 |
|---|---|---|
| continuous | 每秒生成 4 帧，后端抽样观察 | 支持 |
| on_demand | 请求时生成一段新图，其他时间重复最后一帧 | 支持；任务调度 A，无法确认时有界请求 B |
| event_only | 切换场景/模式时生成约 3 秒事件画面 | 明确 unsupported |

模拟中的 transport_online 与 fresh 分开：重复旧图时媒体连接可以在线，但画面已经过期。

## 正式 Adapter 必须补齐

1. 能力 supported / unsupported / unknown，以及探测依据与版本。
2. 物理设备、逻辑通道、采集会话和帧序号；T8214 两镜头是否独立通道待核验。
3. 可信采集时间、时间偏移/误差；SDK 只给接收时间时明确降低证据可信度。
4. 画面尺寸、朝向及 view_revision；云台转动/移动后旧 ROI 不再直接可用。
5. 鉴权、会话刷新、休眠、唤醒、并发与频率限制、命令回执。
6. 录像回放的原始时间与回放时钟，不能把录像时间改成当前时间假装实时。

以上是下一阶段接口要求，当前没有伪造这些字段的真机支持结果。替换时保留 domain.py 的证据和状态原则，适配器负责提供真实可验证的数据；必要时扩展合同并复验。

SDK 首测顺序：各取一张真正新图 → 两设备同时观察 → A 遮挡请求 B → 无效/超时命令 → 断流恢复 → 关闭控制 App 后任务继续。SDK 平台可能决定是否需要本地网关或原生移动端桥，当前不作平台兼容承诺。

# 传送带红点检测（可选）

功能位于 OpenRAIL 客户端，所有现有 YAML 默认关闭。关闭时 Control、推理和相机按原有流程工作，模型服务启动命令不变。

## 使用

1. 重启网页客户端并刷新页面。在 Camera Viewer 的三路相机下方找到“传送带红点检测”。
2. Observe Start 开启原始图像观察。Control 停止时勾选检测，展开“检测配置”。
3. 填入 5 个 ROI：`[[x,y,宽,高], ...]`，坐标以原始头部图像 1280×800 为准。配置延迟停止秒数 n，点击“应用检测配置”。默认 ROI 为 `[]`，未填完不能启动自动控制。
4. 查看五张 ROI 拼图、每个点的可见状态/红色连通区域面积。区域应只包含对应红点，避免包裹、机械臂上的红色干扰。
5. 点击 Control Start 启用自动运行：至少 3 个点连续可见 0.5 秒后，先获取新动作再开始执行。
6. 可见点少于 3 个时继续工作 n 秒，再暂停推理与动作；期间重新出现至少 3 个点则取消倒计时。暂停期间保持观察和检测。
7. 红点再次满足恢复条件，清除旧动作、等待新观测和新动作块后恢复，不重置子任务进度。
8. 人工 Control Stop 会取消自动恢复，即使点全部可见也不启动。再次运行需要手动 Control Start。人工 Pause、Reset、Observe Stop 和控制故障同样取消自动运行。

自动等待时 Control 按钮仍显示 Stop，用于取消本轮授权。检测配置只能在 Control 已停止、旧动作清理完成后修改。页面勾选/应用立即生效；需要下次启动保留时，使用配置面板 Save 保存到当前 YAML。

## YAML

配置位于当前客户端文件的 `vision.conveyor_gate`，例如 `conf/lingbot_ori_package.yaml`：

```yaml
vision:
  conveyor_gate:
    enabled: false
    camera: cam.head
    reference_size: [1280, 800]
    rois: []
    min_visible: 3
    stop_delay_s: 2.0
    resume_stable_s: 0.5
    detect_hz: 10.0
    frame_timeout_s: 0.5
    hsv_red_ranges: [[0, 10], [170, 179]]
    saturation_min: 100
    value_min: 60
    min_blob_area_px: 20
```

ROI 坐标为整数。检测使用原始 BGR 图像上的 HSV 红色范围及最大连通区域；面积阈值以参考分辨率像素计算。同视野、同宽高比的帧会缩放到参考分辨率；改变头部视角后需要重新配置 ROI。`min_visible`、阈值和稳定时间可在 YAML 修改。

遮罩/裁剪仅用于模型或其预览，不影响此检测。五张图作为独立诊断预览，通过 `/api/client/conveyor` 约 5 Hz 刷新，不添加为模型相机输入。启用检测且 Observe 运行时即可预览；自动控制判断由 Control Start 授权。

相机超时会直接暂停，不继续 n 秒。控制故障不会由红点清除；现有 SDK 控制故障锁存仍需人工处理。软件暂停停止下发后续目标，不是底层硬件急停。

## 验证与范围

实现包括离线 ROI 检测、延迟/稳定时间状态机、人工停止优先、暂停前在途推理结果清理、新动作等待、禁用模式原路径、前端接口及已有 ORI/夹爪回归测试。未连接机器人测试自动运动，5 个真实 ROI 尚待现场标定。

```bash
../lingbot-vla/.venv/bin/python -m pytest -q tests/test_conveyor_gate.py
```

传送台归位仍由固定 ROI 的红点可见性判断，需要现场确认移动途中不会误满足条件。初始参数只是配置起点，n 和面积阈值以现场画面调整。

# G1 通信环境恢复

Open-RAIL 的 G1 客户端使用 `.venv` 中的 `a2d_sdk` 1.5.0、Cosine DDS 和图像订阅接口。PC forwarder 是 ROS 桥接，不是 Python SDK 订阅的必经接口。恢复后的路径不再引用相邻的旧 `g1` 仓库。

## 路径

- Python：`.venv/bin/python`（Python 3.10，现存 SDK 和依赖继续使用）。
- 厂商运行文件：`hardware/g1/vendor_packages/a2d_sdk-1.5.0/forwarder/app/`。
- SSH 密钥：`.local/robot/orin_g1_ed25519`；通过 `ORIN_KEY` 可覆盖。
- 模式配置：`hardware/g1/conf/{idle,copilot}.pbtxt`。
- 日志：`.local/robot/log/`。

`hardware/g1/vendor_packages/` 和 `.local/` 已加入 Git 忽略规则，私钥不会随代码提交。SDK wheel 安装包不在恢复内容中；不要把 `hardware/g1/setup_g1_env.sh` 当作日常启动命令，它用于持有完整安装包时重建虚拟环境。

## 只读通信验证

```bash
hardware/g1/g1_check_communication.sh
```

此命令只创建订阅者，检查 14 维关节反馈、左右夹爪、整机状态及头部/左右手图像。每路需要至少两个递增时间戳，并满足 0.5 秒新鲜度要求。输出 `communication_ok: true` 表示通信通过，不表示已完成动作安全、控制权或故障验收。整机状态中的错误及急停标志会原样输出。

现存客户端入口继续 source `hardware/g1/g1_pc_gdk_env.sh`。该环境按到 `10.42.0.101` 的路由选择 `LOCATOR_IP`，固定 Aorta discovery、`USE_PTP_CLOCK=OFF`、ROS domain 0 和 localhost 模式。

## 模式切换及 forwarder

```bash
hardware/g1/g1_restore_runtime_layout.sh
hardware/g1/g1_enter_copilot.sh
# 仅在只读检查通过、现场准备好之后：
hardware/g1/g1_enter_copilot.sh --execute --confirm SWITCH_FROM_VR_TO_COPILOT
```

布局脚本复制模式配置并建立 SDK 启动适配脚本；不会安装厂商二进制或依赖。切换入口在发送 IDLE 前检查 forwarder 和动态库、SDK 导入、SSH 与 Orin 模式服务。缺少任何依赖时拒绝切换，避免先停止仍能工作的旧 bridge。切换后核验 Orin COPILOT 组件，并用直接 SDK 订阅验证状态和相机。

模式配置来自本仓库历史提交 `f0905f9`，其中 COPILOT 内容与旧仓库读取历史一致。该历史提交中的 forwarder 版本较旧、库不完整，不作为实际恢复二进制使用。

## 2026-10-15 恢复进度

- 原有修改已保存为 `b8faa7a`；相关离线测试在 LingBot 虚拟环境下为 32 通过、2 跳过。
- 从旧 forwarder PID 1378413 持有的已删除文件中恢复原版可执行文件及 98 个动态库；可执行文件 SHA256 与旧进程一致。
- 管理员已完成动态库保存与 SONAME 链接恢复；`ldd` 依赖检查通过。新 SSH 密钥已获 Orin `agi` 授权，模式服务为 active。
- 旧进程已退出，新 forwarder PID 4020191 从 Open-RAIL 内恢复目录独立启动。重启后 SDK 实测：14 维关节、双夹爪、状态和三路图像连续更新；头部 800×1280、双手 480×848。ROS `/hal/arm_joint_state` 也收到真实样本。
- 模式切换入口的只读预检通过，Orin `genie_motion_control` 和 `camera_copilot` 已在运行。没有执行 idle→COPILOT 切换或机器人动作；未进行整机重启测试。
- 通信通过时观察到 `neck_error=4294967295`，这里只记录值，没有将它判定为正常或下发清错命令。通信恢复不等于运动安全验收。
- 本次恢复的是已验证的通信运行组件，不是完整厂商安装包；动态加载但尚未使用的扩展组件及 ROS 自定义消息 Python 包不保证完整。

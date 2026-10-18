# G1 硬件与通信

此目录集中管理这台 G1 的环境加载、通信检查、模式切换、PC forwarder 和模式配置。模型推理与网页客户端仍从仓库根目录的 `scripts/run_lingbot_*.sh` 启动；机器人 Python 适配器仍在 `client/robots/agibot_g1/`。

所有命令从 Open-RAIL 根目录执行。

## 日常使用

只读检查关节、左右夹爪、整机状态和三路相机：

```bash
hardware/g1/g1_check_communication.sh
```

输出 `communication_ok: true` 表示各路数据连续更新且时间戳新鲜，不代表控制权或运动安全验收。

准备一个终端的 SDK 环境（客户端启动脚本已自动完成这一步）：

```bash
source hardware/g1/g1_pc_gdk_env.sh
```

切换模式前先检查依赖与 SSH 服务：

```bash
hardware/g1/g1_enter_copilot.sh
```

确实需要切换且已停止自动控制时：

```bash
hardware/g1/g1_enter_copilot.sh --execute --confirm SWITCH_FROM_VR_TO_COPILOT
```

该命令会经过 IDLE 切换至 COPILOT，并启动 PC forwarder。已在 COPILOT、只缺少本机桥接时，可在单独终端启动并保持终端打开：

```bash
hardware/g1/ros_env_wrapper.sh start
```

自动控制结束后如需停止桥接，执行 `hardware/g1/ros_env_wrapper.sh stop`。

## 文件用途

| 文件 | 用途 | 使用时机 |
| --- | --- | --- |
| `g1_pc_gdk_env.sh` | 加载 Python、ROS、通信库、网络发现和时间设置 | 客户端自动 source；也可手动 source |
| `g1_check_communication.sh` / `.py` | 仅订阅，验证实时反馈和图像 | 日常检查；不发动作、不切模式 |
| `g1_enter_copilot.sh` | SSH 预检、显式模式切换及反馈验证 | 需要进入 COPILOT 时 |
| `ros_env_wrapper.sh` | 启停本机 ROS ↔ Cosine forwarder | 需要 ROS 桥接时 |
| `g1_restore_runtime_layout.sh` | 生成运行目录中的配置副本和启动适配器 | 恢复文件或移动仓库目录后 |
| `setup_g1_env.sh` | 用完整厂商 wheel 安装包创建或重建 `.venv` | 安装维护；不是日常启动命令 |
| `conf/idle.pbtxt`、`conf/copilot.pbtxt` | 模式切换请求配置 | 由恢复布局脚本复制到厂商运行目录 |
| `RECOVERY.md` | 本次恢复来源、验证结果和限制 | 排障参考 |

## forwarder 与依赖位置

```text
hardware/g1/
├── README.md
├── RECOVERY.md
├── *.sh / g1_check_communication.py
├── conf/
│   ├── idle.pbtxt
│   └── copilot.pbtxt
└── vendor_packages/                  # 本机文件，Git 忽略
    └── a2d_sdk-1.5.0/
        ├── conf/                    # 模式配置副本
        ├── scripts/ros_env_wrapper.sh
        └── forwarder/app/
            ├── bin/forwarder        # 从原存活进程恢复的原版程序
            └── lib/                 # 恢复的 98 个动态库及 SONAME 链接
```

实际可执行文件：

```text
/home/bjtc/Sophix/g1-open-rail/hardware/g1/vendor_packages/a2d_sdk-1.5.0/forwarder/app/bin/forwarder
```

这是原版文件的恢复与迁移，没有升级厂商版本。已有 Git 历史中的旧版二进制没有用于运行。

Python SDK 仍位于仓库 `.venv/lib/python3.10/site-packages/a2d_sdk/`。SSH 私钥保持在 `.local/robot/orin_g1_ed25519`，运行日志在 `.local/robot/log/`；二者不入 Git。`GDK_DIR` 和 `ORIN_KEY` 可覆盖默认位置。

SDK 的 RobotDds 与 CosineCamera 直接通过网线通信；forwarder 提供 ROS 桥接。SSH 同样走网线，用于 Orin 服务及模式组件检查，不承载 SDK 的反馈与图像。

## 兼容与恢复边界

旧 `scripts/g1_*.sh`、`scripts/ros_env_wrapper.sh`、`scripts/setup_g1_env.sh` 保留为转发入口。根目录 `vendor_packages` 是指向本目录的兼容链接，实际文件只有一份。`scripts/run_a2d_sdk.zsh` 也转向维护中的模式脚本，无参数时只检查。

本机恢复的是已验证可运行的通信组件，不是完整厂商安装包；从 Git 克隆不会自动获得动态库、私钥或 `.venv`。重建环境仍需匹配架构的厂商 wheel。移动整个仓库后需重新运行 `g1_restore_runtime_layout.sh`，以更新 SDK 的启动适配器路径。

通信已验证，但未做机器人动作或整机重启测试。整机状态曾报告 `neck_error=4294967295`，本次没有将其判定为正常或执行清错。

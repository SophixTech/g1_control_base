# LingBot-VLA 与 G1 部署

所有部署入口均从 Open-RAIL 的 `scripts/` 启动。模型服务和机器人客户端使用独立环境，通过 ZMQ 通信。

| 进程 | 解释器 | 运行依赖 |
| --- | --- | --- |
| G1 网页客户端、RobotProxy | `g1-open-rail/.venv/bin/python`（Python 3.10） | 本仓库 `pyproject.toml` 的 Web、数值处理、记录与通信依赖，以及厂家 SDK wheel、Protobuf 3.12.4、ruckig 0.14.0 |
| LingBot 模型服务 | `lingbot-vla/.venv/bin/python`（现有 Python 3.12） | 原模型及 GPU 依赖，加 Open-RAIL 服务依赖；保留现有环境 |

客户端需要 Linux 和厂家对应架构的 `cp310` 通信 wheel，因此使用 Python 3.10。网页和 RobotProxy 子进程都使用仓库内 `.venv`，不再使用 G 仓库的虚拟环境。模型、权重、厂家原始安装文件仍放在原目录，不复制到 Git。

## 创建客户端环境

已安装 uv 时，在 Open-RAIL 根目录运行：

```bash
scripts/setup_g1_env.sh
source .venv/bin/activate
```

脚本使用 `uv venv` 创建 `.venv`，再用 `uv pip install` 安装本项目及 SDK。uv 的环境与安装方式见[官方文档](https://docs.astral.sh/uv/pip/environments/)。

- 默认基础解释器为 `/usr/bin/python3.10`，可用 `OPEN_RAIL_BASE_PYTHON` 覆盖。
- 默认厂家目录为相邻 `g1/vendor_packages/a2d_sdk-1.5.0`，可用 `GDK_DIR` 覆盖。需要其中的 `a2d_sdk`、`genie_msgs_pb`、对应架构的 `cosine_bus` wheel。
- `UV_BIN` 可指定 uv 路径。本机 uv 安装于 `~/.local/bin/uv`。
- ruckig 若需要源码构建，脚本固定兼容的构建工具范围，默认最多使用 2 个编译任务。
- `.venv/` 已被 Git 忽略；脚本不改原 GDK 或 LingBot 训练环境。
- 此流程使用 uv 的 pip 接口；不要直接 `uv sync`，因为厂家 wheel 尚未写入项目依赖清单，可能被同步操作移除。

核心依赖版本以 `pyproject.toml` 为准，包括 NumPy 1.26.4、OpenCV 4.11.0.86、pandas 2.2.3、PyArrow 18.1.0、SciPy 1.15.3、WebSockets 16.0。SDK 安装沿用厂家 wheel，Protobuf 与 ruckig 版本在安装脚本中明确指定。

## G1 客户端

环境准备已迁入本仓库：

```bash
source scripts/g1_pc_gdk_env.sh
```

它激活本地 `.venv`，加载厂家 `env.sh` 提供的日志、库路径和 ROS 设置，再按到 `10.42.0.101` 的路由选择本机 IP，设置发现服务、网段与 `USE_PTP_CLOCK=OFF`。不再调用 `G/g1_pc_gdk_env.sh`。仍需保留厂家底层运行目录；其 `env.sh` 可能刷新 ROS daemon。

客户端启动脚本会自动执行上述准备，无需重复 source：

```bash
scripts/run_lingbot_g1_client.sh --host 127.0.0.1 --port 9000
```

**M08 创建 `conf/lingbot_package.yaml`，并完成 M05～M07 后，再执行完整任务。** 配置缺失时脚本停止，不回退到默认任务。网页地址为 `http://127.0.0.1:9000`。

COPILOT 模式与机器连接仍按现有现场流程准备，本脚本不自动切换模式或发送动作。G 的旧控制入口不能与 Open-RAIL 同时执行。

## 模型端

从 Open-RAIL 根目录运行，显式填写同一训练任务的权重、统计文件和动作步数：

```bash
scripts/run_lingbot_server.sh \
  --model_path /path/to/hf_ckpt \
  --norm_path /path/to/norm_stats.json \
  --chunk_size 25 \
  --num_denoising_step 10
```

`chunk_size` 支持 25 / 50；25 步使用已有专用模型类，不能用截取输出代替。`num_denoising_step` 是独立的采样迭代次数。

可通过 `LINGBOT_REPO_PATH`、`LINGBOT_PYTHON`、`QWEN25_PATH` 覆盖模型源码、解释器及 tokenizer 路径。脚本默认使用相邻 LingBot 仓库的 `.venv`，tokenizer 默认位于相邻 `models/Qwen2.5-VL-3B-Instruct-tokenizer`。服务只创建一个模型实例和一个推理工作线程，无需原 WebSocket 模型服务。

## 当前状态

- M01/M02：模型适配器、服务入口和启动脚本已接入。
- M03：26 项假模型测试通过；真实 GPU 推理按用户要求暂缓，避免影响训练。
- M04：客户端入口与环境准备脚本已迁入 Open-RAIL。本地 Python 3.10 `.venv` 已由 uv 创建，47 个包的依赖检查通过；Web 应用、VLAClient、RobotProxy、RobotBody 和 SDK 导入及网页入口 `--help` 通过。完整网页与真机验收仍待任务配置和后续适配。

- M05：观测状态与图像颜色已适配，9 项离线测试通过。
- M06：双臂使用绝对目标；左夹爪保持采样值，右夹爪保留四次方处理；发送前检查反馈和整机状态。新增 36 项假 SDK 测试通过。

- M07：开始／恢复执行前调用 `prepare_policy_control()`；重复开始不重新采样，准备失败不启用控制。新增 6 项测试通过。

包含现有暂停／代理异步控制回归测试，共 82 项通过，1 项真实模型测试跳过；未加载 GPU 模型或连接机器人。

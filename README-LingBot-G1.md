# LingBot + G1 真机启动

M01～M08 已完成代码迁移与离线验证；真实模型推理及真机闭环尚未验收。以下命令供现场执行，本次仅整理文档，没有执行这些启动命令。

客户端使用本仓库 `.venv`，模型使用 `lingbot-vla/.venv`。机器人保持固定底盘位置；自动执行不发送轮子、头和腰的运动命令。模式切换使用本仓库 `scripts/g1_enter_copilot.sh`；软包归位暂时仍调用原 G1 脚本。

## 1. 环境检查（终端 A）

```bash
cd /home/bjtc/Sophix/g1-open-rail
source scripts/g1_pc_gdk_env.sh
python --version
ping -c 3 10.42.0.101
```

作用：激活本地客户端环境，设置 GDK 网络与时钟环境，检查机器人网络。

预期：出现 `GDK ready`、Python `3.10.x`，机器人 IP 能收到回复。此步骤不发送运动命令。当前 `.venv` 已安装；只有缺失或重建时，先运行 `scripts/setup_g1_env.sh`。

## 2. 进入 COPILOT（终端 A，已就绪则跳过）

使用已迁入本仓库的入口，先只读检查：

```bash
cd /home/bjtc/Sophix/g1-open-rail
scripts/g1_enter_copilot.sh
```

预期：`Dry run complete: no robot mode was changed.`。它通过 SSH 检查 Orin 模式服务，不切换机器人模式。

该入口使用本仓库 `scripts/g1_pc_gdk_env.sh` 和 `.venv/bin/python`。厂家目录默认仍为相邻 `g1/vendor_packages/a2d_sdk-1.5.0`，SSH 密钥默认仍为相邻 `g1/orin_g1_ed25519`；可分别用 `GDK_DIR`、`ORIN_KEY` 指定其他位置。密钥不复制到 Open-RAIL。 模式切换入口已通过语法检查和 4 项离线模拟验证，尚未实际切换真机。

现场确认机器人静止、无人使用 VR 后执行：

```bash
scripts/g1_enter_copilot.sh \
  --execute --confirm SWITCH_FROM_VR_TO_COPILOT
```

作用：切换 `idle → COPILOT`，并尝试启动 PC forwarder；预计需等待约一分钟。`Robot is ready` 是阶段信号，后面仍需在网页确认真实相机和关节反馈。切换时不要运行旧 G1 推理执行程序或 Open-RAIL 控制。 若只读检查提示 Orin 常驻模式服务未启动，按原 `g1/g1_install_orin_mode_service_fix.sh` 的安装修复流程处理；该修复工具尚未迁入。

若没有实际 forwarder、后续无法取得反馈，另开终端运行以下备用命令；已有实例时不要重复启动：

```bash
cd /home/bjtc/Sophix/g1-open-rail
scripts/ros_env_wrapper.sh start
```

作用：自动加载 Open-RAIL 的 GDK 环境，前台运行机器人通信桥；无需另外 source，保持此终端打开。已有 forwarder 时提示已运行，不再重复启动。脚本不切换机器人模式。

停止前先结束自动控制，再在 Open-RAIL 根目录运行：

```bash
scripts/ros_env_wrapper.sh stop
```

此命令沿用原工具的行为，终止匹配 `/forwarder/app/bin/forwarder` 的桥接进程，不匹配同目录中的 `ros2` 工具。厂家二进制及库仍使用现有 GDK 安装目录，可通过 `GDK_DIR` 指定；操作入口已迁入本仓库。

## 3. 软包初始位姿（需要归位时，启动网页机器人组件之前）

网页 G1 `Reset` 使用 Default 软包初始位姿，不受手动面板的勾选或 Custom 选择影响。Python 默认配置和 `lingbot_package.yaml` 已与原脚本对齐：腰部俯仰 `0.491126 rad`、升降 `44.752 cm`，头部 `[-0.257285, 0.428170] rad`，双臂采用原脚本目标，夹爪采用原始反馈值除以 `120`。修改后须重启 Web 客户端并刷新网页，使机器人子进程重新加载配置。

网页 Reset 仅对齐目标姿态，仍使用网页原有运动方式：双臂轨迹规划，头和腰通过 SDK 直接提交目标，**不等同于原脚本的 60 秒慢速恢复**。需要原有慢速恢复及到位检查时，在网页机器人组件启动前使用下面的原脚本，不能与其他机器人控制程序同时运行。

```bash
cd /home/bjtc/Sophix/g1-open-rail
source scripts/g1_pc_gdk_env.sh
python /home/bjtc/Sophix/g1/运控test/g1_pc_move_to_package_target_pose.py
```

作用：只读预演，输出当前位姿、目标和建议时长，不发送运动命令。

下面命令会真实移动双臂、头、腰及夹爪，不移动轮子。原目标头部俯仰约 `24.53°`，超过原脚本记录的 `20°` 文档上限；仅在现场已确认该目标例外、空间与急停条件后使用：

```bash
python /home/bjtc/Sophix/g1/运控test/g1_pc_move_to_package_target_pose.py \
  --duration-s 60 \
  --execute \
  --confirm MOVE_G1_TO_PACKAGE_TARGET_POSE \
  --allow-head-pitch-over-document-limit
```

预期：约 60 秒缓慢到达软包位姿并保持；脚本检查状态和最终到位误差。它不会把被推走的底盘恢复到原位置。等待脚本退出后再启动网页中的机器人组件。

## 4. 启动模型服务（独立终端 B）

此步骤会加载 GPU 模型；若主机仍在训练，先安排好 GPU 使用。下面以已核对的 **25 步候选权重**为例，实际使用哪份权重由这三个参数共同决定：

```bash
cd /home/bjtc/Sophix/g1-open-rail
scripts/run_lingbot_server.sh \
  --model_path /home/bjtc/Sophix/lingbot-vla/output/separated_model/mixed_conditioned_chunk25/checkpoints/global_step_10000/hf_ckpt \
  --norm_path /home/bjtc/Sophix/datasets/marked_9_1_0922_chunk25/train_stats/norm_stats.json \
  --chunk_size 25 \
  --num_denoising_step 10
```

作用：加载 LingBot，提供本机 ZMQ `5566` 推理服务；本身不连接或驱动机器人。

预期：模型加载完成后出现 `Start to receive data and infer...`，等待客户端请求。保持终端打开。

如改用已核对的 50 步候选，三个参数一起替换：

| 参数 | 50 步取值 |
| --- | --- |
| `--model_path` | `/home/bjtc/Sophix/lingbot-vla/output/separated_model/mixed_conditioned/checkpoints/global_step_10000/hf_ckpt` |
| `--norm_path` | `/home/bjtc/Sophix/datasets/marked_9_1_0922/train_stats/norm_stats.json` |
| `--chunk_size` | `50` |

`num_denoising_step=10` 是本示例的推理采样次数，与 25／50 步动作长度不同。换新 checkpoint 时使用对应统计文件和训练动作长度，客户端仍按 30Hz 播放。

## 5. 启动网页客户端（独立终端 C）

```bash
cd /home/bjtc/Sophix/g1-open-rail
scripts/run_lingbot_g1_client.sh --host 127.0.0.1 --port 9000
```

作用：自动准备客户端环境，加载 `conf/lingbot_package.yaml`，启动网页服务。此命令本身不开始机器人运动。使用空闲的 `9000` 端口；现有入口会清理占用指定端口的进程。

预期：终端出现 `GDK ready` 和 Uvicorn 启动日志。本机浏览器打开 <http://127.0.0.1:9000>，任务应为 `package_a2d`，指令为：

> Pick a soft package from the box, orient its label upward, and place it on the conveyor belt.

## 6. 网页按顺序启用

首次使用按 `Observe → Infer → Control` 分步操作；不要直接点启动全部流程的 `Start`。每步确认成功再继续，各按钮是开／关切换，重复点击会关闭对应功能。

| 操作 | 效果 | 预期现象 |
| --- | --- | --- |
| `Observe` | 创建机器人组件，读取观测 | 头部和左右腕部图像持续更新，关节状态更新；不执行模型动作 |
| `Infer` | 将真实观测交给模型 | 模型端推理计数增长，客户端显示推理耗时／预测；机器人仍不执行模型动作 |
| `Control` | 开始实际自动执行 | 先检查状态并采样左夹爪保持值；双臂跟随目标，右夹爪经四次方处理后开合，左夹爪保持 |
| `Pause` | 暂停观测、推理与自动控制 | 不再提交后续自动动作；软件暂停不等同于硬件急停 |
| `Resume` | 恢复暂停前启用的功能 | 若恢复控制，会重新读取左夹爪保持值；并非无条件开启控制 |
| `Stop` | 停止客户端并释放组件 | 网页仍可保留，模型终端仍在运行 |

若启用控制时报 `stale`、故障、急停或控制状态错误，先处理对应状态，再继续；不要跳过检查。动作异常时使用现场实体急停。

## 7. 记录与退出

### 单关节诊断日志（不需要开启数据集录制）

需要比较模型目标、实际下发与反馈时，由操作者在**下次启动 Web 客户端**时启用：

```bash
scripts/run_lingbot_g1_client.sh --host 127.0.0.1 --port 9000 --trace-joint 7
```

`--trace-joint 0..6` 对应左臂第 1..7 关节，`7..13` 对应右臂第 1..7 关节；上例记录右臂第 1 关节。不传该参数则关闭诊断，不修改当前速度、控制周期或运动行为。开启 Observe、创建机器人组件时，终端会打印 `Joint trace enabled: ...`；每次创建客户端组件生成独立目录 `logs/joint_traces/<时间戳_随机后缀>/`。可用 `--trace-dir` 指定根目录。诊断与 `record.switch` 独立。

日志包含以下信息：

- `client.jsonl`：每个模型块的全部原始关节目标、该关节输入状态、请求/返回时间、动作时间间隔、实际使用的 speed/周期/衔接模式；每条提交目标、规划速度/加速度、块 ID、块内时间、指令 ID；Control 启停及运行时倍率修改。
- `robot.jsonl`：真正进入 `move_arm()` 的关节目标及 SDK 调用起止时间，继承同一指令 ID；被队列新目标取代的记录；SDK 异常；SDK 原始关节反馈和设备采样时间戳。手动/Reset 的手臂 SDK 调用也记录，标记为 `manual`，没有模型块对应关系。

两个进程使用同一 PC 的 `perf_counter_ns` 比较时序，同时记录墙上时钟。反馈以 PC 读取到它的时刻定位，并保留设备时间戳；**不假定机器人设备时钟与 PC 同步。SDK 调用返回不代表电机收到指令或已经执行。** 日志不具备机器人内部执行器指令/确认信息。

正常 Stop 并退出客户端后，由操作者生成离线对比报告（不会连接机器人或模型）：

```bash
python3 scripts/analyze_joint_trace.py logs/joint_traces/<本次目录>
```

输出 `report.html`、`commands.csv`、`feedback.csv`、`summary.json`。用浏览器打开 HTML 即可同时查看：原始模型预测、客户端提交目标、SDK 调用目标、真实反馈、目标差异、命令目标变化率与实测差分速度。图表可选择模型块和时间范围，全部资源内嵌，无需启动服务。

`commands.csv` 的模型参考值按**同一模型块、同一规划时间偏移**在原始点间线性插值；这不是 Open-RAIL 的三次插值结果，因此“提交目标 − 模型参考”包含插值及块间衔接的作用，不能直接当成模型错误。`SDK目标 − 提交目标` 用于核对最后下发是否改变。最近反馈的读取时间、设备时间戳和距下发时间也单独给出；不是把旧反馈当成同步执行结果。

报告对每次 Control 开始估计首次可观测运动：下发前 250 ms 至少有 3 个稳定反馈样本，随后连续 3 个不同设备时间戳样本偏离基准至少 `0.002 rad` 才标记。阈值可用 `--motion-threshold-rad` 调整。若此前已经运动、反馈不足或没有超过阈值，显示未知/未检测到；所标时间是 **PC 首次观察到持续反馈变化**，不是精确电机启动时间或逐条指令执行确认。

日志通过有界队列异步写盘，队列满时丢诊断记录而不阻塞控制；结束标记记录丢失数量。写盘失败会在终端报错，缺少结束标记、缺失文件或未确认下发的指令会在报告中提示。异常退出可能丢失末尾数据。开启诊断仍有采样和序列化开销；未做真机性能验收。轨迹日志用于分析，不是限速器，也不会改变模型目标。

记录默认关闭。在网页选择所需记录类型并开启，数据保存在 `data/lingbot_package` 下；状态 20 维、动作 16 维。记录动作是提交给机器人代理的目标，尚未经过执行侧左夹爪替换和右夹爪四次方处理。

结束时先在网页 `Pause`／`Stop`，等待组件停止，再在客户端和模型终端分别按 `Ctrl-C`。若手动运行了 forwarder，最后在 Open-RAIL 根目录执行 `scripts/ros_env_wrapper.sh stop` 结束该桥接进程。

常用参数在 `conf/lingbot_package.yaml`：`vla_zmq.ip/port` 是模型地址，`infer_timeout=10000` 毫秒是暂定超时（首次请求为其 4 倍），需按真实推理耗时调整；`gripper_freq=9` 表示每 9 次实际控制调用发一次夹爪命令。

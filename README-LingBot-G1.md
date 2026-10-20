# LingBot + G1 部署速查

总结：

启动网页后依次按“obs start”“inference start”，前两个只启动推理，按“control start”后真机开始运动

“reset”恢复抓包裹默认姿态
“resume”基于当前状态继续执行

如果希望减缓机器运行速度，同步调整wait time以及speed

可用参数：

较快：speed = 1 、wait time=10

较慢：speed = 0.5、 wait time=300

## 1. 检查连接（终端 A）

机器人连接 PC 的 Debug 网口。检查网络和显存：

```bash
cd /home/bjtc/Sophix/g1-open-rail
ping -c 3 10.42.0.101
nvidia-smi
```

机器人须能 ping 通。模型与自标注/训练共用 GPU，显存不足时先结束或等待其他 GPU 任务。

硬件脚本、模式配置与 forwarder 已集中到 [`hardware/g1/`](hardware/g1/README.md)。现有 `.venv` 可直接使用；仅在持有完整厂商 wheel 安装包且需要重建环境时执行 `hardware/g1/setup_g1_env.sh`。

机器人已在 COPILOT 时，可先只读验证关节、夹爪和三路相机：

```bash
hardware/g1/g1_check_communication.sh
```

输出 `communication_ok: true` 表示通信正常，不代表已经授权运动。

## 2. 切换 COPILOT（终端 A，已就绪则跳过）

下面命令切换机器人模式并尝试启动通信桥（forwarder）：

```bash
cd /home/bjtc/Sophix/g1-open-rail
hardware/g1/g1_enter_copilot.sh --execute --confirm SWITCH_FROM_VR_TO_COPILOT
```

如果没有forwarder，在单独终端运行并保持打开：

```bash
cd /home/bjtc/Sophix/g1-open-rail
hardware/g1/ros_env_wrapper.sh start
```

## 3. 启动模型（终端 B）

修改下面四个参数；示例使用 50 步模型。此命令只提供推理，不控制机器人。

**任务prompt可以在之后启动的网页中进行热修改，不需要在启动推理服务时候修改**

```bash
cd /home/bjtc/Sophix/g1-open-rail

MODEL_PATH="/home/bjtc/Sophix/lingbot-vla/output/separated_model/mixed_conditioned/checkpoints/global_step_10000/hf_ckpt"
NORM_PATH="/home/bjtc/Sophix/datasets/marked_9_1_0922/train_stats/norm_stats.json"
CHUNK_SIZE=50
DENOISING_STEPS=10

scripts/run_lingbot_server.sh \
  --model_path "$MODEL_PATH" \
  --norm_path "$NORM_PATH" \
  --chunk_size "$CHUNK_SIZE" \
  --num_denoising_step "$DENOISING_STEPS"
```

| 参数 | 含义 / 替换要求 |
|---|---|
| `MODEL_PATH` | 模型权重目录，指向 `hf_ckpt` |
| `NORM_PATH` | 与该模型训练数据对应的 `norm_stats.json` |
| `CHUNK_SIZE` | 模型训练的动作长度：25 或 50；不能任意更改 |
| `DENOISING_STEPS` | 推理去噪次数，与动作长度不同 |

等待出现 `Start to receive data and infer...`，保持终端打开。默认端口 **5566**；已有模型服务时不要重复启动。

## 4. 启动网页控制（终端 C）

```bash
cd /home/bjtc/Sophix/g1-open-rail
scripts/run_lingbot_g1_client.sh --host 127.0.0.1 --port 9000
```

打开 **http://127.0.0.1:9000**。保持终端打开。

--trace-joint 8 可选参数，加入会自动记录该关节信息

`--trace-joint`：左臂 0～6，右臂 7～13；8 是右臂第二关节。不需要日志则删除该参数。端口占用时先退出对应旧服务。

## 5. 网页操作

依次点击，每一步确认正常后再继续；不要直接点击总 `Start`。

| 按钮 | 作用 / 检查项 |
|---|---|
| `Observe` | 读取机器人；确认三路图像和关节反馈持续更新 |
| `Reset`（需要时） | 移动到软包默认位姿，包括双臂、头、腰及夹爪 |
| `Infer` | 开始模型推理；确认推理耗时/预测更新，此时不执行模型动作 |
| `Control` | 开始真机执行模型处理后的目标 |
| `Pause` | 暂停观测、推理和控制；不是硬件急停 |
| `Resume` | 恢复暂停前的功能，可能立即恢复运动 |
| `Stop` | 停止客户端组件；独立模型服务仍在运行 |

`Observe`、`Infer`、`Control` 是开关按钮，再点一次会关闭。

常用控制参数在 `conf/lingbot_package.yaml`，可以在网页修改，也可以修改yaml后重启客户端

网页修改控制参数 ***“一定一定一定”*** 要点“APPLY”,否则不会生效

## 6. 退出与查看日志

先点网页 **Stop** 并等待停止，再在网页和模型终端分别按 **Ctrl+C**。

生成并打开最新一次关节报告（有 `--trace-joint` 记录后执行）：

```bash
cd /home/bjtc/Sophix/g1-open-rail
TRACE_DIR=$(ls -td -- logs/joint_traces/*/ | head -n 1)
python3 scripts/analyze_joint_trace.py "$TRACE_DIR"
xdg-open "$TRACE_DIR/report.html"
```

报告顶部手动选择“预测块”，查看模型预测、提交目标、SDK目标和真机反馈。SDK调用成功不代表电机已到位。

如需停止通信桥（forwarder），在自动控制结束后执行：

```bash
cd /home/bjtc/Sophix/g1-open-rail
hardware/g1/ros_env_wrapper.sh stop
```

## 可选训练图像裁剪（ORI / NEWARTI）

在原有**模型服务端**启动命令后增加 `--image_profile crop_1016`，例如：

```bash
scripts/run_lingbot_ori_server.sh \
  --model_path /path/to/checkpoint \
  --norm_path /path/to/norm_stats.json \
  --image_profile crop_1016
```

NEWARTI 的 `scripts/run_lingbot_newarti_server.sh` 同样支持此参数。使用实际权重及其训练统计路径替换示例；修改配置后需重启模型服务，停止当前 Control 后再切换，避免混用旧动作队列。

| 参数 | 图像处理 |
| --- | --- |
| `--image_profile original`（默认） | 保留现有输入，不额外裁剪；模型自身的 resize 和归一化照常执行。 |
| `--image_profile crop_1016` | 头部先统一为 768×480，再裁 `(x=200,y=0,w=480,h=480)`；左腕裁 `(184,0,480,480)`；两路缩放到 224×224，右腕保留原路径。 |

尺寸均为宽×高。裁剪模式只接受头部 1280×800 或 768×480，以及左右腕 848×480；其他尺寸（含已裁剪的 224×224）报错，避免误裁和重复处理。处理位于模型适配层，客户端原始画面与记录不变，也不修改 state、action 或 Reset 位姿。启动日志显示 profile，首次处理各相机时打印源尺寸、ROI 和输出尺寸。

头部初次缩放使用 Pillow Lanczos，ROI 缩放使用 Pillow Bicubic。几何视野与 `crop_1016.py` 对齐，但 Pillow 与训练 FFmpeg 的缩放实现、JPEG/H.264 压缩存在差异，不保证逐像素相同。上线前应以实际训练视频抽帧核对；本项离线测试不代表已经完成实机模型推理验收。NEWARTI 若另行显示 ECOT bbox，裁剪坐标不能直接叠加到原始头部画面，需先逆变换。

## 右夹爪开合诊断

在**客户端**启动命令增加参数（与模型服务的图像裁剪参数无关）：

```bash
scripts/run_lingbot_ori_g1_client.sh --trace-gripper right --trace-dir logs/gripper_traces
# NEWARTI 使用 scripts/run_lingbot_newarti_g1_client.sh，参数相同。
```

`--trace-gripper right` 与 `--trace-joint` 互斥。启动会创建独立会话子目录并打印路径。正常停止 Control 后退出客户端，使异步日志完成落盘。随后可导出 CSV：

```bash
python3 scripts/export_gripper_trace.py logs/gripper_traces/实际会话目录
```

| 文件 / 事件 | 含义 |
| --- | --- |
| `client.jsonl` / `model_chunk` | 收到的模型 action chunk 中第 15 维右夹爪序列（索引从 0 开始），含 chunk ID。 |
| `client.jsonl` / `command_submit` | 平滑、融合、偏移后提交给机器人子进程的逐步目标。 |
| `robot.jsonl` / `sdk_command` | 实际调用 SDK 成功返回的右夹爪目标 `q`；含曲线前 `input_target`、chunk/command ID 和调用时间。成功返回不等于机器人已到位。 |
| `robot.jsonl` / `gripper_skipped` | 因 `gripper_freq` 发送分频而跳过该步夹爪下发。 |
| `robot.jsonl` / `feedback` | 每次观测轮询读取的右夹爪原始反馈；用 PC 时间比较，可包含重复值。SDK 的成对反馈时间戳属于左夹爪，已单独标注，不作右夹爪时间戳。 |
| `robot.jsonl` / `sdk_error`、`command_discard`、`control_error` | 调用失败、队列丢弃或控制异常。 |
| `gripper.csv` | 上述事件按 PC 时间整理，模型 chunk 展开为每个预测步；预测步的计划时间在 `planned_offset_s`，并非实际发送时间。 |

当前 fitting 配置下：夹爪先用半窗口 4（最多 9 点）滑动平均，再在 `<0.05` / `>0.95` 时吸附到 0 / 1，随后对相邻过滤值取平均以填充控制采样。`gripper_offset=5` 提前选取后续 5 个处理后采样的目标，不是 5 个原始模型帧。机器人层每 9 次控制调用发送一次夹爪指令（`gripper_freq=9` 是分频，不是 9 Hz）。

右夹爪发送前将值限制在 0～1，并执行 `g(x)=x^4/(x^4+(1-x)^4)`，会放大 0.5 附近的变化。左夹爪在自动控制时保持启动时采样的位置。以上处理本次均未修改。

定位时按 `model_chunk → command_submit → sdk_command → feedback` 比较：先确认模型是否已经反复预测开合，再检查处理和映射后变化，最后比较实际响应。反馈是原始位置量，SDK 命令是 0～1，不能直接计算两者差值。旧 `analyze_joint_trace.py` 只适用于手臂弧度日志，不用于夹爪。

### 网页展示裁剪视野

模型服务使用 `--image_profile crop_1016` 时，客户端可增加：

```bash
scripts/run_lingbot_ori_g1_client.sh --preview-image-profile crop_1016
```

头部、左腕预览采用模型相同的 ROI/缩放规则，右腕保持原图。预览从实际传输 JPEG 解码后处理，只用于显示，额外 JPEG 编码可能有轻微像素差异；推理传输和原始记录不变，服务端仍只裁剪一次。两个进程的参数需配对设置；客户端预览参数不会自动开启服务端裁剪。恢复默认显示可省略该参数或使用 `--preview-image-profile original`。

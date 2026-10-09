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

客户端环境缺失时才执行：`scripts/setup_g1_env.sh`。

## 2. 切换 COPILOT（终端 A，已就绪则跳过）

下面命令切换机器人模式并尝试启动通信桥（forwarder）：

```bash
cd /home/bjtc/Sophix/g1-open-rail
scripts/g1_enter_copilot.sh --execute --confirm SWITCH_FROM_VR_TO_COPILOT
```

如果没有forwarder，在单独终端运行并保持打开：

```bash
cd /home/bjtc/Sophix/g1-open-rail
scripts/ros_env_wrapper.sh start
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
scripts/ros_env_wrapper.sh stop
```

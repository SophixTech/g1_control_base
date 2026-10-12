# LingBot ECOT → Open-RAIL → G1

ECOT 使用独立模型名 `lingbot_ecot`、适配器和配置。原 `lingbot_vla` 的适配器及启动脚本不需要修改。当前接入只输出机器人动作；三个辅助 head 随 checkpoint 严格加载，但不输出辅助预测，也不参与任务切换或控制。

## 1. 独立范围与当前验证状态

| 项目 | 原 LingBot | ECOT |
|---|---|---|
| 模型适配器 | `server/models/lingbot_vla/` | `server/models/lingbot_ecot/` |
| 模型源码 | `../lingbot-vla` | `../worktrees/branch-ecot` |
| 模型配置命名空间 | `models.lingbot_vla` | `models.lingbot_ecot` |
| 客户端配置 | `conf/lingbot_package.yaml` | `conf/lingbot_ecot_package.yaml` |
| prompt 文件 | `conf/lingbot_package_language.json` | `conf/lingbot_ecot_package_language.json` |
| ZMQ 端口（交替使用） | 5566 | 5566 |
| Web 启动脚本默认端口 | 由原脚本参数决定，示例9000 | 9001 |
| 可视化端口（与现有前端一致） | 8765 | 8765 |
| 数据保存目录 | `data/lingbot_package` | `data/lingbot_ecot_package` |

两个模型交替运行，切换前先停止原模型服务，复用配置中的 ZMQ 5566 端口。每次启动使用独立服务进程；ECOT 适配器不继承、不导入旧适配器。源码包重名，因此不支持在同一 Python 进程中先后加载两套实现。发现来自其他 checkout 的 `deploy` 或 `lingbotvla` 模块时直接报错，不删除模块缓存强行切换。

模型脚本默认复用用户提供的 `../lingbot-vla/.venv/bin/python`，但通过 ECOT 专用源码路径加载模型。这实现源码、配置和运行状态隔离，**不是依赖环境隔离**。若需要分别升级 PyTorch/Transformers 等依赖，设置 `ECOT_PYTHON` 指向独立安装并验证过的环境。ECOT 脚本不使用 `LINGBOT_REPO_PATH`、`LINGBOT_PYTHON` 等旧模型专用变量。

2026-10-09：checkpoint 配置、归一化维度和 safetensors 权重头检查通过。离线适配及旧模型回归测试通过。当前环境 `nvidia-smi` 无法连接驱动，尚未完成真实权重实例化、GPU 推理对照和真机验证；不能据此宣称部署已验收。

## 2. 启动 ECOT 推理服务

```bash
cd /home/bjtc/Sophix/g1-open-rail
scripts/run_lingbot_ecot_server.sh \
  --model_path /home/bjtc/Sophix/worktrees/branch-ecot/output/ecot1003_10000_20261008/checkpoints/global_step_10000/hf_ckpt \
  --norm_path /home/bjtc/Sophix/datasets/marked_9_1_0922/train_stats/norm_stats.json \
  --chunk_size 50 \
  --num_denoising_step 10
```

该命令启动 Open-RAIL 的 ZMQ 模型服务，不是原生 WebSocket 服务。不要把 `python -m deploy.lingbot_vla_policy` 的 WebSocket 端口直接填入 ZMQ 客户端。

可选环境变量：

- `ECOT_REPO_PATH`：ECOT 源码 checkout。默认 `../worktrees/branch-ecot`。
- `ECOT_PYTHON`：模型 Python 解释器。
- `ECOT_TOKENIZER_PATH`：默认 `../models/Qwen2.5-VL-3B-Instruct-tokenizer`。

服务按单个推理 worker 访问模型，防止同一 policy 的可变状态并发冲突；客户端仍然异步执行。默认 `rtc_mode=off`、`use_compile=False`。完整权重由原生 ECOT loader 重建 LoRA 后 `strict=True` 加载。不要用忽略不匹配参数的方式跳过 ECOT head。

## 3. ECOT 客户端

沿用原 G1 部署文档中的设备及通信准备步骤。先停止其他向同一机器人发送指令的客户端，再使用 ECOT 入口：

```bash
cd /home/bjtc/Sophix/g1-open-rail
scripts/run_lingbot_ecot_g1_client.sh --trace-joint 8
```

打开 `http://127.0.0.1:9001`。网页加载 `lingbot_ecot_package.yaml`，连接5566端口。启动 Web 本身不开始动作；初始化 Client 后，先用 Observe/Infer 检查数据，再由操作者启用 Control。不要同时让新旧客户端控制同一机器人。

独立配置的初始值为 `async`、四次 `fitting`、原 `min_jerk`、`speed=0.5`、`wait_time=300 ms`、控制周期3.75 ms。它们是测试起点，不是新模型实测得到的最优参数。推理超时暂设10000 ms，需根据新模型的实际延迟评估。旧模型的配置不随之改变。

prompt 与 ECOT 当前训练代码的条件式任务指令一致：标签朝上直接放置，朝下才翻转。无需把 ECOT 的 bbox/阶段真值作为输入，也不要使用旧配置里的“无条件翻转”prompt 替换它。

夹爪仍使用通用 G1 驱动中当前的左夹爪保持、右夹爪曲线处理；这不是 ECOT 专用模型逻辑。第一阶段没有更改该驱动或块间融合。

## 4. 验证

离线接口测试（不调用模型或机器人）：

```bash
cd /home/bjtc/Sophix/g1-open-rail
/home/bjtc/Sophix/lingbot-vla/.venv/bin/python -m pytest -q \
  tests/test_lingbot_ecot_adapter.py
```

GPU 可用时，对已保存的一帧观测执行真实推理并比较原生 policy 输出。下例目录必须存在 `g1.rollout.raw.v2` 格式的 `episode.json`、`inference_observations.jsonl` 和对应图像；测试不连接机器人：

```bash
cd /home/bjtc/Sophix/g1-open-rail
QWEN25_PATH=/home/bjtc/Sophix/models/Qwen2.5-VL-3B-Instruct-tokenizer \
ECOT_TEST_REPO_PATH=/home/bjtc/Sophix/worktrees/branch-ecot \
ECOT_TEST_MODEL_PATH=/home/bjtc/Sophix/worktrees/branch-ecot/output/ecot1003_10000_20261008/checkpoints/global_step_10000/hf_ckpt \
ECOT_TEST_NORM_PATH=/home/bjtc/Sophix/datasets/marked_9_1_0922/train_stats/norm_stats.json \
ECOT_TEST_OBSERVATION_DIR=/home/bjtc/Sophix/g1/runtime_rollouts/0930-2 \
/home/bjtc/Sophix/lingbot-vla/.venv/bin/python -m pytest -q -s \
  tests/test_lingbot_ecot_adapter.py::test_real_saved_observation_matches_native
```

测试检查严格加载、50×16有限动作、相同随机种子下包装接口与原生接口输出一致，以及输入图像/状态不被修改。真实测试通过后仍需评估新模型的推理延迟和真机轨迹，不应沿用旧模型日志作为新模型效果证据。

## 5. 切回旧模型

停止 ECOT 客户端和模型服务，再使用原 `run_lingbot_server.sh` 和 `run_lingbot_g1_client.sh`。原模型配置、prompt、源码入口均未被新适配器改写；无需给旧适配器增加模式开关。

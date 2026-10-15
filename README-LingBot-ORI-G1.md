# ORI LingBot → Open-RAIL → G1

适配源码：`/home/bjtc/Sophix/ORI-lingbot-vla`。使用独立模型名 `lingbot_ori`、适配器、客户端配置、prompt 和启动脚本。适配代码均位于 Open-RAIL 仓库，无需修改 ORI 源码或正在传输的 checkpoint。

## 启动

checkpoint 传输并解压完成后，`--model_path` 指向包含 `config.json`、`lingbotvla_cli.yaml` 和完整 `*.safetensors` 的目录，不是 ZIP 或训练中间状态目录：

```bash
cd /home/bjtc/Sophix/g1-open-rail
scripts/run_lingbot_ori_server.sh \
  --model_path /absolute/path/to/hf_ckpt \
  --norm_path /home/bjtc/Sophix/datasets/mixed_conditioned_data/train_stats/norm_stats.json \
  --chunk_size 50 --num_denoising_step 10
```

示例统计路径来自 ORI 的 `configs/vla/package_posttrain.yaml`；必须与实际 checkpoint 的训练数据一致。适配器要求 `package_a2d`、50 步完整微调权重，不接受 ECOT 或 LoRA checkpoint。原生 loader 使用 `strict=True` 加载。

```bash
scripts/run_lingbot_ori_g1_client.sh --trace-joint 8
```

打开 `http://127.0.0.1:9002`。客户端连接 Open-RAIL ZMQ 5566，复用可视化端口 8765。切换模型时停止占用这些端口的旧服务及旧客户端。初始化后先检查 Observe/Infer，再由操作者启用 Control。

客户端复制本次提交时 ECOT 的实际参数：async、fitting 四次拟合、min_jerk、speed=0.8、wait_time=100 ms、控制周期 3.75 ms、推理超时 10000 ms。这些是沿用值，尚未针对 ORI 实测调优。数据保存在 `data/lingbot_ori_package`。

## 指令选择

`conf/lingbot_ori_package_language.json` 保留 ORI 训练代码的两条原文，`auto_mode=false`：

- `sub_task_id=0`（默认）：保持标签朝上放到传送带。
- `sub_task_id=1`：翻转使标签朝上，再放到传送带。

按当前任务在客户端选择指令。ORI 训练使用 episode 标签选择这两条指令；本适配不自动识别朝向，也没有 ECOT 辅助 head，因此没有复用 ECOT 的统一条件式 prompt。

## 接口和环境

输入为三路 RGB uint8 图像与 16/20 维状态，仅前 16 维进入模型：左臂 7、右臂 7、左/右夹爪各 1。输出为 50×16 有限绝对目标；原生 FeatureTransform 已恢复手臂绝对值，适配器不重复叠加状态。图像和状态复制后传给原生接口，避免其原地预处理修改客户端输入。

ORI 原生构造函数没有 `rtc_mode`；适配器仅重写 reset 中的配置定位，使用 ORI checkout 的绝对机器人 YAML 路径，不改变进程工作目录；同时将 YAML 字典形式的 joints 转成原生解析器需要的字符串形式，兼容 CLI 导出的字符串配置。模型实例单 worker 串行推理。每次切换源码使用新进程，检测到其他 checkout 的同名包会报错。

环境变量：`ORI_REPO_PATH`（默认 `../ORI-lingbot-vla`）、`ORI_PYTHON`（默认 `../lingbot-vla/.venv/bin/python`）、`ORI_TOKENIZER_PATH`（默认 `../models/Qwen2.5-VL-3B-Instruct-tokenizer`）。共享解释器不等于依赖隔离；已验证该解释器能从 ORI checkout 导入原生 policy。

## 验证状态

2026-10-12：离线测试共 25 项通过，2 项真实推理测试跳过；脚本语法及服务 `--help` 检查通过。mixed_conditioned 统计维度符合接口要求，ORI 原生 FeatureTransform 已在 Open-RAIL 工作目录下初始化通过。当前 checkpoint 仍为传输中的 ZIP，尚未验证实际权重；`nvidia-smi` 无法连接驱动，尚未完成 GPU 推理及真机验收。

```bash
/home/bjtc/Sophix/lingbot-vla/.venv/bin/python -m pytest -q tests
```

权重就绪后可单独运行不加载 CUDA 的元数据和分片长度检查：

```bash
/home/bjtc/Sophix/lingbot-vla/.venv/bin/python - <<'PY'
from server.models.lingbot_ori import ModelVLA
print(ModelVLA.validate_artifacts(dict(
    repo_path='/home/bjtc/Sophix/ORI-lingbot-vla',
    model_path='/absolute/path/to/hf_ckpt',
    norm_path='/home/bjtc/Sophix/datasets/mixed_conditioned_data/train_stats/norm_stats.json',
    chunk_size=50, num_denoising_step=10,
)))
PY
```

GPU 可用后，使用已有 `g1.rollout.raw.v2` 观测运行离线真实推理对照（不连接机器人）：

```bash
QWEN25_PATH=/home/bjtc/Sophix/models/Qwen2.5-VL-3B-Instruct-tokenizer \
ORI_TEST_REPO_PATH=/home/bjtc/Sophix/ORI-lingbot-vla \
ORI_TEST_MODEL_PATH=/absolute/path/to/hf_ckpt \
ORI_TEST_NORM_PATH=/home/bjtc/Sophix/datasets/mixed_conditioned_data/train_stats/norm_stats.json \
ORI_TEST_OBSERVATION_DIR=/absolute/path/to/saved_episode \
/home/bjtc/Sophix/lingbot-vla/.venv/bin/python -m pytest -q -s \
  tests/test_lingbot_ori_adapter.py::test_real_saved_observation_matches_native
```

该测试检查严格加载、有限动作、相同随机种子下适配与原生 infer 的输出一致及输入未被修改。完成后再评估推理耗时与真机轨迹。

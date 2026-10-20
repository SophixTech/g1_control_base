# ORI LingBot → Open-RAIL → G1

适配源码：`/home/bjtc/Sophix/ORI-lingbot-vla`。使用独立模型名 `lingbot_ori`、适配器、客户端配置、prompt 和启动脚本。适配代码均位于 Open-RAIL 仓库，无需修改 ORI 源码或正在传输的 checkpoint。

## 启动

`--model_path` 指向包含 `config.json`、`lingbotvla_cli.yaml` 和完整 `*.safetensors` 的权重目录。`--norm_path` 必须使用该 checkpoint **训练时同一份统计文件**，不能仅凭数据集名称选择。ORI 适配器要求 `package_a2d`、50 步完整微调权重，不接受 ECOT 或 LoRA checkpoint。

### 裁剪测试：10-18-cut0922

先停止 Control 并退出占用端口的旧模型服务和旧客户端，再在两个终端分别启动。

**终端 1：模型服务（开启实际推理裁剪）**

```bash
cd /home/bjtc/Sophix/g1-open-rail
scripts/run_lingbot_ori_server.sh \
  --model_path /home/bjtc/Sophix/ORI-lingbot-vla/trained-model/10-18-cut0922/hf_ckpt \
  --norm_path /home/bjtc/Sophix/ORI-lingbot-vla/trained-model/10-18-cut0922/norm.json \
  --chunk_size 50 \
  --num_denoising_step 10 \
  --image_profile crop_1016
```

**终端 2：网页客户端（裁剪预览 + 右夹爪记录）**

```bash
cd /home/bjtc/Sophix/g1-open-rail
scripts/run_lingbot_ori_g1_client.sh \
  --preview-image-profile crop_1016 \
  --trace-gripper right \
  --trace-dir logs/gripper_traces
```

打开 **http://127.0.0.1:9002**。先启动 Observe 检查三路画面，再启动 Inference 检查推理；由操作者确认后启动 Control。Reset 使用 `conf/lingbot_ori_package.yaml` 的 Default 位姿，与图像裁剪参数独立。

| 参数 | 作用 |
| --- | --- |
| 服务端 `--image_profile crop_1016` | 裁剪真正送入模型的头部、左腕图像。 |
| 客户端 `--preview-image-profile crop_1016` | 网页显示同样裁剪视野；仅处理显示副本，不改变推理传输，避免重复裁剪。 |
| 客户端 `--trace-gripper right` | 记录右夹爪模型 chunk、处理后目标、SDK 下发值和原始反馈。 |

**两个裁剪参数需要配对设置。网页显示裁剪画面，不代表服务端已经开启裁剪。**

裁剪规则：头部 1280×800 先缩放为 768×480（已是该尺寸则跳过），再裁 `(x=200,y=0,w=480,h=480)`；左腕 848×480 裁 `(184,0,480,480)`。头部和左腕输出 224×224；右腕保持原图，后续仍经过模型自身的 resize。未知源尺寸会报错。网页预览经过额外 JPEG 编码，不保证与模型输入逐像素相同。客户端与服务端均需 Pillow，已列入项目依赖。

夹爪日志保存在 `logs/gripper_traces/时间戳_会话编号/`。停止控制并退出客户端后，可导出：

```bash
python3 scripts/export_gripper_trace.py logs/gripper_traces/实际会话目录
```

不需要夹爪日志时去掉两个 `--trace-*` 参数。若改记手臂，可替换为 `--trace-joint 8`（右臂第 2 关节）；它与 `--trace-gripper` 互斥。

### 不裁剪模式

选择对应的训练权重及 norm，将服务端参数改为 `--image_profile original`，客户端参数改为 `--preview-image-profile original`；省略这两个参数也都默认为 `original`。切换后重启对应进程，以免沿用旧配置和动作缓存。

客户端网页端口为 9002，模型 ZMQ 端口为 5566，可视化端口为 8765。如报 `address already in use`，先查占用进程并退出旧客户端：

```bash
ss -ltnp 'sport = :9002'
```

客户端运行参数以 `conf/lingbot_ori_package.yaml` 和网页当前设置为准，记录目录为 `data/lingbot_ori_package`。

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

# NEWARTI → Open-RAIL → G1

这份文档用于 `/home/bjtc/Sophix/ORI-lingbo-vla-newarti` 的 `package_ecot_full.yaml` 训练路线。使用独立模型名 `lingbot_newarti`。目前尚无训练权重：接口模拟测试通过，实际权重加载、GPU 推理和真机效果尚未验证。

不能只替换 ECOT 文档中的权重路径。旧 ECOT 适配要求 LoRA；旧 ORI 适配拒绝 ECOT 参数。newarti 使用完整权重，除了阶段、框、标签朝向预测，还可启用可见性预测，并将这些预测通过投影层传入动作生成。新适配调用 newarti 自己的 `sample_actions`，保留这条计算路径，不在 Open-RAIL 重写网络。

## 启动模型服务

训练完成后，准备 Hugging Face 格式的 `hf_ckpt` 目录，包含 `config.json`、`lingbotvla_cli.yaml` 和完整 `.safetensors` 权重。训练使用 DCP 保存时，需要先按模型仓库的导出流程转换；不能直接把 DCP 目录作为模型目录。

以下 `/实际路径/` 必须替换为导出目录和该次训练实际使用的统计文件，不能把其他模型的统计文件随意搭配使用：

```bash
cd /home/bjtc/Sophix/g1-open-rail
scripts/run_lingbot_newarti_server.sh \
  --model_path /实际路径/checkpoints/global_step_10000/hf_ckpt \
  --norm_path /实际路径/norm_stats.json \
  --chunk_size 50 \
  --num_denoising_step 10
```

仓库中 `package_ecot_full.yaml` 当前填写的统计文件是 `/home/bjtc/Sophix/datasets/marked_9_1_0922/train_stats/norm_stats.json`；以后以导出 checkpoint 的训练配置为准。

脚本默认使用：

- 模型源码：`../ORI-lingbo-vla-newarti`，可通过 `NEWARTI_REPO_PATH` 指定。
- Python：`../lingbot-vla/.venv/bin/python`，可通过 `NEWARTI_PYTHON` 指定独立环境。这是复用依赖环境，不是复用旧模型源码。
- tokenizer：`../models/Qwen2.5-VL-3B-Instruct-tokenizer`，可通过 `NEWARTI_TOKENIZER_PATH` 指定。
- 模型服务端口：ZMQ 5566；切换前停止原来占用此端口的模型服务。

模型加载保持原生 `strict=True`。辅助头、可见性头和动作条件投影层按训练开关加载；启用的结构必须有对应权重。只支持 50 步、package_a2d、非 LoRA 完整权重。没有 RTC，也没有额外的模型 WebSocket 服务。模型实例的推理请求串行处理，机器人客户端仍可异步执行。

## 启动 G1 客户端

按原 G1 文档完成设备、COPILOT 和 forwarder 准备，再启动：

```bash
cd /home/bjtc/Sophix/g1-open-rail
scripts/run_lingbot_newarti_g1_client.sh --trace-joint 8
```

浏览器打开 `http://127.0.0.1:9000`。相机仍使用 8765；远程端口转发需同时转发 9000 和 8765。只运行一个 G1 客户端。网页启动本身不执行动作；先检查 Observe 和 Infer，再由操作者开启 Control。

配置在 `conf/lingbot_newarti_package.yaml`，数据写入 `data/lingbot_newarti_package`。机器人控制、平滑、暂停、记录继续使用现有实现。这次适配没有新增头部或腰部运动调用。

## 任务指令必须与训练一致

newarti 数据加载器按照抓取前的标签朝向选择两条指令，新配置提供两个独立任务：

| 网页任务 ID | 使用场景 | 发给模型的指令 |
|---|---|---|
| `package_label_up`（初始选择） | 抓取前标签朝上 | Pick the soft package from the box and place it on the conveyor belt, keeping the label facing up. |
| `package_label_down` | 抓取前标签朝下 | Pick the soft package from the box, flip it so the label faces up, and place it on the conveyor belt. |

根据本次包裹初始状态手动选择任务，两个任务不是连续执行的两个阶段。现有部署入口不会自动根据辅助头切换任务。推理不需要输入 bbox 或阶段真值；模型内部根据图像和状态产生条件预测。不要用旧 ECOT 的合并条件指令替代这两条训练指令。

## 新增代码的职责

| 文件 | 职责 |
|---|---|
| `server/models/lingbot_newarti/lingbot_newarti.py` | 按 newarti 配置检查完整权重，加载该源码的原生 policy；三路 RGB 图像与前 16 维状态传入模型，返回 50×16 动作和原观测时间戳。原生代码负责图像预处理、归一化恢复及手臂增量恢复为绝对角度，适配器不重复加状态。 |
| `conf/models_conf.py`、`run_server.py` | 注册 `lingbot_newarti` 模型与独立参数，使用一个推理 worker。 |
| `scripts/run_lingbot_newarti_server.sh` | 选择模型源码、依赖环境和 tokenizer，启动 ZMQ 模型服务。 |
| `scripts/run_lingbot_newarti_g1_client.sh` | 准备 GDK 环境，加载新客户端配置，在 9000 启动网页。 |
| `conf/lingbot_newarti_package.yaml`、同名前缀的 language JSON | 独立客户端参数、保存目录，以及训练中的两条任务指令。 |
| `tests/test_lingbot_newarti_adapter.py` | 模拟检查输入输出、时间戳、源代码隔离、必要权重和配置一致性；提供后续真实推理对照入口。 |

适配以 ORI 为模板，旧 ORI/ECOT 适配器和启动脚本保持原样。一次模型服务进程只加载一套源码，避免同名 `lingbotvla` 包混用。

## 验证与后续

```bash
cd /home/bjtc/Sophix/g1-open-rail
/home/bjtc/Sophix/lingbot-vla/.venv/bin/python -m pytest -q \
  tests/test_lingbot_newarti_adapter.py \
  tests/test_lingbot_ori_adapter.py \
  tests/test_lingbot_ecot_adapter.py
```

2026-10-14：43 项通过，3 项真实推理测试因未提供权重／观测路径跳过。两个启动脚本通过 Bash 语法检查。模拟测试不证明真实权重可成功加载。

有模型后，可设置 `NEWARTI_TEST_REPO_PATH`、`NEWARTI_TEST_MODEL_PATH`、`NEWARTI_TEST_NORM_PATH`、`NEWARTI_TEST_OBSERVATION_DIR`，以及 `QWEN25_PATH`，运行：

```bash
/home/bjtc/Sophix/lingbot-vla/.venv/bin/python -m pytest -q -s \
  tests/test_lingbot_newarti_adapter.py::test_real_saved_observation_matches_native
```

观测目录需为 `g1.rollout.raw.v2` 格式，包含 `episode.json`、`inference_observations.jsonl` 和图像。该测试只读保存的观测，在同一随机种子下比较适配接口和原生 policy 输出，不连接机器人。通过后再评估新模型实际延迟和真机行为。

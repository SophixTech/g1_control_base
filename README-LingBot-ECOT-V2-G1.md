# ECOT V2 在 G1 上部署

本入口适配 `/home/bjtc/Sophix/worktrees/branch-ecot-v2`：Qwen2.5-VL + 预测标签逐层 K/V 条件。模型类型为 `lingbot_ecot_v2`，与旧 `lingbot_ecot` 和 Qwen3-VL 的 `lingbot_v2` 分别配置。

## 权重准备

需要从该分支训练并导出的 **package_a2d、50 步** checkpoint：

```text
hf_ckpt/
├── config.json
├── lingbotvla_cli.yaml
└── *.safetensors
```

`lingbotvla_cli.yaml` 放在权重目录内部；使用同一次训练的真实配置和 norm，不要拿当前源码中的示例 YAML 替代。支持完整微调和 LoRA；LoRA 类型由 `train.use_lora` 决定，原生 loader 严格加载全部参数。需要导出的 Hugging Face 权重，不能直接传 FSDP/DCP 的训练恢复目录。

有效模型配置必须启用 `ecot_aux_supervision=true`、`ecot_label_kv_conditioning=true`，关闭 `ecot_action_conditioning`。权重必须包含标签 K/V 投影及相应辅助头；启用 visibility 时也检查 visibility 头。旧 ECOT 或 ORI 权重不能用于此入口。

当前分支的 `configs/vla/package_multi_posttrain.yaml` 使用 `meanstd`，历史 `ecot1003.yaml` 使用 `bounds_99`；部署按 checkpoint 保存的 `data.norm_type` 处理，`--norm_path` 必须是对应训练统计。本地分支目录目前没有可直接使用的 checkpoint，下面两个路径需要替换。

## 不裁剪启动

终端 1：模型服务。

```bash
cd /home/bjtc/Sophix/g1-open-rail
scripts/run_lingbot_ecot_v2_server.sh \
  --model_path /实际训练输出/checkpoints/global_step_60000/hf_ckpt \
  --norm_path /该次训练使用的/norm_stats.json \
  --chunk_size 50 \
  --num_denoising_step 10 \
  --image_profile original
```

终端 2：G1 网页客户端。

```bash
cd /home/bjtc/Sophix/g1-open-rail
scripts/run_lingbot_ecot_v2_g1_client.sh \
  --preview-image-profile original
```

打开 **http://127.0.0.1:9002**。服务使用 ZMQ 5566。启动前退出占用相同端口的旧模型服务及客户端；硬件通信环境沿用 [G1 通信说明](hardware/g1/README.md)。

## 裁剪启动

仅在训练图像也经过 `crop_1016` 处理时，用这组命令作为对应部署。当前分支配置指向 0922 数据，不能仅凭分支名判定它使用了裁剪图。

终端 1：

```bash
cd /home/bjtc/Sophix/g1-open-rail
scripts/run_lingbot_ecot_v2_server.sh \
  --model_path /实际训练输出/checkpoints/global_step_60000/hf_ckpt \
  --norm_path /该次训练使用的/norm_stats.json \
  --chunk_size 50 \
  --num_denoising_step 10 \
  --image_profile crop_1016
```

终端 2：

```bash
cd /home/bjtc/Sophix/g1-open-rail
scripts/run_lingbot_ecot_v2_g1_client.sh \
  --preview-image-profile crop_1016
```

服务端参数决定模型输入裁剪；客户端参数仅决定网页预览，发送给服务端的观测仍为原图，因此不会重复裁剪。头部、左腕裁剪后为 224×224，右腕保留原图；之后仍经过原生模型预处理。切换时重启两端。

需要记录右夹爪时，在客户端命令追加：

```bash
--trace-gripper right --trace-dir logs/gripper_traces
```

## 配置与数据流

- 源码默认 `worktrees/branch-ecot-v2`，可通过 `ECOT_V2_REPO_PATH` 覆盖。
- Python 默认 `/home/bjtc/Sophix/lingbot-vla/.venv/bin/python`，可通过 `ECOT_V2_PYTHON` 覆盖。复用依赖环境，模型源码从目标分支导入。
- Qwen2.5 tokenizer/config 默认 `/home/bjtc/Sophix/models/Qwen2.5-VL-3B-Instruct-tokenizer`，可通过 `ECOT_V2_TOKENIZER_PATH` 覆盖。
- 客户端配置：`conf/lingbot_ecot_v2_package.yaml`。从当前 ORI 配置复制控制参数和 Default 位姿，语言文件及录制目录独立。Reset 的左右臂位姿在 `robots.agibot_g1.action_layout.arm.presets.left/right.Default` 修改。
- 指令文件：`conf/lingbot_ecot_v2_package_language.json`，使用该分支训练代码中的完整固定 prompt。网页不需要人工选择 label-up/down；预测标签概率由模型内部生成并用于动作注意力。辅助头不用于网页自动判定 subtask 完成。
- 输入为当前三路 RGB、14 个臂关节及两个夹爪值。每次推理返回新的 `(50,16)` 动作块，顺序为左臂 7、右臂 7、左夹爪、右夹爪。
- 使用目标分支原生 `FeatureTransform.unapply` 去除模型补零、反归一化并将手臂增量恢复为绝对目标；夹爪保持绝对值。OpenRAIL 不再重复叠加当前位姿。
- 原生 RTC 关闭，沿用 OpenRAIL 的异步轨迹执行和块间融合；同一模型实例只运行一个推理线程。

## 验证范围

离线测试覆盖 LoRA/完整微调、旧权重及缺失 K/V/visibility 参数拒绝、配置和源码隔离、裁剪、连续动作块、时间戳及输出格式。另用目标分支真实 CPU `FeatureTransform` 验证 75→16 维逆变换，检查手臂仅叠加一次状态、夹爪不叠加状态。

```bash
cd /home/bjtc/Sophix/g1-open-rail
../lingbot-vla/.venv/bin/python -m pytest -q tests/test_lingbot_ecot_v2_adapter.py
```

本次没有加载真实 ECOT V2 checkpoint、执行 GPU 推理或下发机器人动作；离线测试通过不等于已验证真实权重的行为效果。

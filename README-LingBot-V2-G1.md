# LingBot V2 在 G1 上部署

Open-RAIL 新增独立模型类型 `lingbot_v2`，对应相邻目录 `ORI-lingbot-vlaV2` 的 Qwen3-VL 版本。旧 LingBot、ECOT、ORI、NEWARTI 的模型入口保持原样。模型交替使用，切换时停止旧服务并启动新服务；ZMQ 继续使用 5566。

## 启动

先准备 **V2 在 package_a2d 上训练的 checkpoint** 及该次训练使用的归一化统计。不要把旧 ORI 权重传给 V2。当前本地 V2 仓库尚无 `package_a2d` 训练配置；本次补齐的是 Open-RAIL 部署适配，不包含训练和权重生成。

```bash
scripts/run_lingbot_v2_server.sh \
  --model_path /path/to/run/checkpoints/global_step_10000/hf_ckpt \
  --norm_path /path/to/v2/norm_stats.json \
  --chunk_size 50 \
  --num_denoising_step 10
```

原生 V2 loader 从 `hf_ckpt` 向上三级读取训练配置，目录应为：

```text
run/
├── lingbotvla_cli.yaml
└── checkpoints/
    └── global_step_10000/
        └── hf_ckpt/
            └── *.safetensors
```

该 YAML 的 `model`、`train`、`data` 必须来自此次训练，不能用示例配置替代。完整目录迁移时保留这个结构。`--chunk_size` 支持 25、50，必须等于训练时的动作长度。

启动脚本默认使用：

- 源码：相邻的 `ORI-lingbot-vlaV2`；可用 `LINGBOT_V2_REPO_PATH` 覆盖。
- Python：V2 源码目录内的 `.venv/bin/python`；可用 `LINGBOT_V2_PYTHON` 覆盖。
- Qwen3 资源：相邻的 `models/Qwen3-VL-4B-Instruct`；可用 `QWEN3VL_PATH` 覆盖。

准备好 G1 硬件通信环境后，另一个终端启动客户端：

```bash
scripts/run_lingbot_v2_g1_client.sh
```

网页地址为 `http://127.0.0.1:9002`，客户端配置是 `conf/lingbot_v2_package.yaml`。启动网页不会自动切换机器人模式。控制参数初值复制当前 ORI 配置：`rdm.mode=async`、块内 `fitting`、块间 `min_jerk`；本次不改变融合算法。

`conf/lingbot_v2_package_language.json` 提供取包任务示例。**部署前换成 V2 训练实际使用的完整指令**。图像默认 `--image_profile original`；仅当该 checkpoint 使用对应裁剪数据训练时，选择 `--image_profile crop_1016`。

## V2 适配具体做了什么

1. 使用原生 `deploy.lingbot_vla_v2_policy.LingbotVLAv2Server`。通过 `chunk_ret=True`，每次观测都重新推理并返回完整动作块；避免原生逐点缓存模式反复返回旧块中的单点。
2. 三路 RGB 和当前状态传给 V2 原生图像处理、FeatureTransform 和模型。只提供当前观测；不需要客户端提供未来帧。`num_denoising_step` 设置原生模型的 `config.num_steps`。
3. 机器人映射位于 `server/models/lingbot_v2/package_a2d.yaml`，不依赖旧模型仓库的机器人配置。原始 16 维顺序是左臂 7、右臂 7、左夹爪、右夹爪。
4. 按官方默认 55 维布局，夹爪位于内部 `[28:30)`，不能直接截取前 16 维。使用原生 `FeatureTransform.unapply` 去除补零、反归一化、恢复原始 16 维；手臂恢复绝对角度，夹爪保持绝对值。适配器不会再次叠加当前关节角度。
5. V2 原生映射默认 `relative_type=quaternion_local`，适用于末端位姿。这里显式设置手臂 `relative_type: null`，使用关节角度的加减，避免把关节角当成四元数处理。训练侧 package_a2d 映射也应使用相同设置。
6. 统计文件必须与 V2 训练一致。原生转换支持其训练配置指定的归一化方式；不自动复用旧模型的统计或夹爪映射。

服务只允许一个推理线程，避免同一策略实例的缓存被并发请求修改。客户端仍然异步执行当前轨迹，因此单个推理线程不意味着串行的“执行完再推理”。

## 验证范围

新增离线测试覆盖模型配置隔离、连续观测返回新块、时间戳保留、输出形状、原生 `chunk_ret` 行为，以及 CPU 上的原生 55→16 维动作逆变换。后者用不同的手臂/夹爪值验证夹爪槽位，并验证手臂仅叠加一次当前状态。

```bash
../ORI-lingbot-vlaV2/.venv/bin/python -m pytest -q tests/test_lingbot_v2_adapter.py
```

尚未加载真实 V2 checkpoint、运行 GPU 推理或连接机器人验证。本次已有回归测试中的 `test_lingbot_newarti_adapter.py::test_training_prompts_match` 失败：现有 NEWARTI 指令配置已改成多条，与该测试要求的一条训练指令不符；未改动此配置。

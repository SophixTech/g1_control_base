# LingBot-VLA 与 G1 真机部署迁入 Open-RAIL：分轮执行报告

日期：2026-10-03。

本报告参考 [7-7-FINALMIGRATE.md](./7-7-FINALMIGRATE.md) 的组织方法：先确定接口，再列迁移块，每块写清来源、目标文件、操作和完成标准。参考的是执行清单结构，不照搬其中 N2 训练、ONNX 或硬件重建的任务。

本文是实施方案与执行记录。2026-10-03 已完成 M00 只读核对、M01 模型适配和 M02 服务入口；M03 接口测试已完成，按用户要求暂不加载真实模型，以免影响主机训练。实际启用的 checkpoint 待指定，尚未运行机器人。M04 客户端启动脚本和环境准备已完成，M04a COPILOT 模式切换入口已迁入并通过离线模拟验证，任务配置已由 M08 补齐；M05 图像与状态适配及离线验证已完成；M06 执行侧迁移及 M07 开始／恢复前采样已完成离线验证；M08 任务配置及离线加载验证已完成；M09 真机验收仍待执行。相对于前一份迁移分析，**本报告以直接调用 LingBot 模型代码为唯一实施主线，不再采用 WebSocket 转发，也不迁移 RTC。**

## 0. 目标与改动原则

最终完成这条闭环：

```text
网页开启观测
  → Open-RAIL 从 G1 读取三路图像和关节状态
  → Open-RAIL 模型服务直接调用 LingBot
  → LingBot 返回未来 H 组动作（H 为配置的 chunk_size，首版支持 25 / 50）
  → Open-RAIL 安排动作时间与前后衔接
  → 厂家 SDK 让 G1 执行
  → 新图像和状态进入下一次推理
```

从功能上看，只需要接好两处：

1. **模型入口：**让 Open-RAIL 能调用 `lingbot-vla` 已有的模型加载和推理代码。
2. **机器人出口：**让 Open-RAIL 发给当前 G1 的关节与夹爪命令，符合原软包任务的含义。

连接模型与机器人所需的采集线程、异步推理、定时发送、暂停和记录，Open-RAIL 已经有。迁移通过配置和少量接入代码使用这些能力，不重新写一套执行框架。

执行规则：

- 每轮实际新增或修改的核心文件不超过 3 个。本报告连测试、脚本、任务配置也计入清单，不用“一个目录”代替多个文件来规避数量限制。
- 作为依据阅读的源文件不计入修改数量；每轮明确列出，不能把“阅读”误认为“需要复制”。
- 原 `lingbot-vla` 模型实现和 `g1` 部署脚本先保留。主要改动落在 `g1-open-rail`。
- 不新增 WebSocket 桥接、自动重连系统、多模型插件框架或新的暂停状态机。
- 只检查输入输出维度、有效数值，以及当前机器人已有的必要状态条件。错误应报到现有入口，不以补零、伪造观测或悄悄换模型继续运行。
- 首版同时设计 **25 / 50 组动作模型**的配置入口，实际每次只加载一个明确指定的 checkpoint。`chunk_size` 必须匹配训练配置和统计文件；不将 50 步模型截取前 25 步当作 25 步模型。

## 1. 三个仓库分别负责什么

本文使用三个路径简称：

| 简称 | 绝对路径 | 本次承担的角色 |
| --- | --- | --- |
| L | `/home/bjtc/Sophix/lingbot-vla` | 提供模型加载、图像预处理、推理和动作数值恢复 |
| G | `/home/bjtc/Sophix/g1` | 提供当前机器已采用的网络准备、输入含义、夹爪规则和状态检查，作为迁移依据 |
| O | `/home/bjtc/Sophix/g1-open-rail` | 接管整个部署流程；新增文件主要放在这里 |

### 1.1 面向 L：适配模型 不复制模型实现

直接复用以下功能：

| L 中的文件 | 复用什么 | 迁移时是否改它 |
| --- | --- | --- |
| `deploy/lingbot_vla_policy.py`、`deploy/lingbot_vla_policy_chunk25.py` | 50 步使用 `LingbotVLAServer`，25 步使用 `LingbotVlaChunk25Server`；复用加载、`reset()`、`infer()` | 首版不改 |
| `lingbotvla/data/vla_data/utils.py` | `FeatureTransform` 的输入变换和动作恢复 | 不改，也不复制一套 |
| `configs/robot_configs/package_a2d.yaml` | 状态顺序、相机字段与动作含义 | 继续使用 |

`LingbotVLAServer` 虽然名字带 Server，但它可以在 Python 进程内直接创建和调用。Open-RAIL 调用这个对象，不运行 LingBot 原来的 WebSocket 启动入口。

### 1.2 面向 G：替换部署职责 保留任务含义

| G 中的功能 | 迁移后的处理 |
| --- | --- |
| `g1_pc_gdk_env.sh` 的 SDK 与网络环境准备 | 已迁至 O/scripts，激活 O 的本地 `.venv`；仍引用厂家底层运行目录 |
| `g1_enter_copilot.sh` 模式切换 | 已迁入 `O/scripts/g1_enter_copilot.sh`，复用 O 本地环境；保持独立手动入口，不并入模型启动 |
| `g1_native_vla_deploy.py` 的图像与状态含义 | 适配到 Open-RAIL 的机器人读取与模型输入之间 |
| 同文件的双臂目标、左夹爪保持、右夹爪执行 | 迁入 Open-RAIL G1 机器人适配 |
| 同文件的串行循环、WebSocket 客户端、逐帧 sleep | 由 Open-RAIL 替换，不搬过去 |
| `g1_realtime_chunking.py` 的调度 | 不迁移，使用 Open-RAIL 的异步流程 |
| `g1_rollout_recorder.py` 的文件写入机制 | 不迁移，使用 Open-RAIL 的记录器 |

“替换”指新部署不再运行旧入口，并不要求删除旧文件。

## 2. 先固定输入输出含义

这张表是后续所有轮次共同遵守的接口定义。

| 内容 | 约定 |
| --- | --- |
| 模型输入状态 | 16 个数：左臂 7、右臂 7、左夹爪、右夹爪 |
| 手臂状态单位 | 弧度，即关节角度单位 |
| 模型输入夹爪状态 | 厂家原始反馈值，沿用 G 的 0～120 范围 |
| 图像 | 头、左腕、右腕三路，模型入口为 H×W×3、RGB、uint8 |
| 任务文字 | 软包任务字符串，不使用默认泡茶任务 |
| 模型返回 | `[H,16]`：`H=chunk_size`，首版支持 25 / 50；每个时间点 16 个目标 |
| 模型动作时间间隔 | 训练约定每秒 30 组，相邻约 33.33 毫秒 |
| 返回的手臂目标 | 已经恢复成绝对关节角度，不再加当前位置 |
| 右夹爪命令 | 模型目标限制到 0～1 后，保留 Open-RAIL 四次方处理 |
| 左夹爪命令 | 当前任务不采用模型预测，使用明确采样的保持值；采样时机见 M06、M07 |
| 头、腰、底盘 | 不加入模型的 16 维动作，继续作为手动部分 |
| 机器人完整状态 | 可保留 Open-RAIL 的 20 维状态供网页与记录使用；模型适配器明确取前 16 维 |

对应输入字段：

| Open-RAIL 模型适配器收到的字段 | LingBot 要求的字段 |
| --- | --- |
| `obs['state'][:16]` | `observation.state` |
| `obs['cam.head']` | `observation.images.cam_high_rgb` |
| `obs['cam.hand_left']` | `observation.images.cam_left_wrist_rgb` |
| `obs['cam.hand_right']` | `observation.images.cam_right_wrist_rgb` |
| `obs['language'][0]` | `task` |

取前 16 维建立在读取顺序仍为 `arm, gripper, head, waist` 的前提上。头腰状态保留在机器人侧，不送入该模型。

依据：[L 的任务定义](/home/bjtc/Sophix/lingbot-vla/configs/robot_configs/package_a2d.yaml)、[G 的输入读取](/home/bjtc/Sophix/g1/运控test/g1_native_vla_deploy.py:177)、[O 的 G1 配置](../conf/robots_conf.py:27)。

## 3. 总迁移路线与每轮文件数量

```text
M00 确定模型与任务基线
  → M01 编写直接调用模型的适配器
  → M02 接到 Open-RAIL 模型启动入口
  → M03 验证模型输入输出
  → M04 准备 G1 客户端启动环境
  → M04a 迁移 COPILOT 模式切换入口
  → M04b 迁移 PC forwarder 启停入口
  → M05 对齐真机图像与状态读取
  → M06 对齐双臂和夹爪命令
  → M07 将左夹爪保持值接到执行开始时刻
  → M08 完成本任务配置
  → M09 从网页观测到实机执行逐项验收
```

| 编号 | 面向哪个源仓库 | 适配或替换的功能 | 实际改动文件数 |
| --- | --- | --- | --- |
| M00 | L + G | 只读核对模型与部署参数，记录可配置步数方案 | 1（仅本报告；运行代码 0） |
| M01 | **L** | 适配模型加载、推理与动作恢复 | 3 |
| M02 | **L** | 用 Open-RAIL 服务入口替换原模型 WebSocket 入口 | 2 |
| M03 | **L**，以 G 输入为参照 | 验证输入字段和输出含义 | 1 |
| M04 | **G** | 复用当前机器环境，替换客户端启动命令 | 2 |
| M04a（追加） | **G** | 迁移 COPILOT 模式切换入口，使用 O 本地环境 | 3（含两份文档） |
| M04b（追加） | **G 的厂家 SDK 工具** | 迁移 PC forwarder 启停入口，自动准备 O 环境 | 3（含两份文档） |
| M05 | **G** | 适配图像、关节与夹爪观测 | 最多 3 |
| M06 | **G** | 适配手臂与夹爪执行、必要状态检查 | 2 |
| M07 | **G** | 将左夹爪保持规则接入 O 的控制启用流程 | 2 |
| M08 | **G + L** | 用 O 的任务配置替换旧部署参数 | 2 |
| M09 | **G + L** | 验收闭环，使用 O 的暂停和记录 | 1 |

同一文件可以在不同轮次继续修改，但每轮只完成表中对应的一项功能。遇到必须改第 4 个核心文件的情况，应拆成下一轮，不能把它隐藏在“顺带调整”中。

## 4. M00：确定模型与任务基线

**面向来源：L 的模型与 G 的当前任务。运行代码修改：0 个文件；本轮仅更新本报告，记录核对结果和 25 / 50 步配置设计。**

只读核对：

- `L/deploy/lingbot_vla_policy.py`、`L/deploy/lingbot_vla_policy_chunk25.py` 与 `L/configs/robot_configs/package_a2d.yaml`：确认模型类和输入输出定义。
- `G/README.md` 的原生部署命令：确认实际要使用的权重、归一化统计文件、`QWEN25_PATH` 和推理步数。

要做：

1. 核对候选权重目录、训练 `chunk_size` 及匹配的统计文件，记录后由用户指定实际使用项。旧 README 中存在不同实验命令，不凭“看起来最新”替用户换模型。
2. 保持 `package_a2d`、三路相机和原软包任务文字一致。
3. 记录模型解释器与 GDK 解释器的位置。两者可以不同。
4. 查看三个仓库当前改动，保留已有内容；本轮不重置工作区，也不因写报告自动创建提交。

完成标准：下一轮能明确填写模型路径、统计文件路径、模型源码路径和任务名称，没有“先随便用一个模型再说”的默认替代。

### 4.1 M00 核对记录（2026-10-03）

**状态：只读核对与配置设计完成；实际启用 checkpoint 待用户指定，因此模型选型尚未闭合。** 未执行模型加载、依赖安装、SDK 初始化或真机控制。

已核对的公共基线：

| 项目 | 结果 |
| --- | --- |
| 模型源码 | `/home/bjtc/Sophix/lingbot-vla` |
| 模型解释器 | `/home/bjtc/Sophix/lingbot-vla/.venv/bin/python`，解析为 Python 3.12.3 |
| GDK 解释器 | `/home/bjtc/Sophix/g1/vendor_packages/a2d_sdk-1.5.0/.venv/bin/python`，解析为系统 Python 3.10 |
| QWEN25_PATH | `/home/bjtc/Sophix/models/Qwen2.5-VL-3B-Instruct-tokenizer`，目录存在 |
| 任务定义 | `package_a2d`；16 维状态/动作及三路图像映射与第 2 章一致 |
| 任务文字 | 沿用 G 默认的 `Pick a soft package from the box, orient its label upward, and place it on the conveyor belt.`；特定 checkpoint 的条件化任务文字仍需在 M03 核验 |
| 动作频率 | G 使用 30 FPS；25 步候选的训练数据 `marked_9_1_0922/train/meta/info.json` 也记录 fps=30 |
| 去噪步数 | 拟以 `num_denoising_step=10` 为初始可修改参数，与 G 普通推理示例及 25 步候选训练 YAML 的 `train.num_steps=10` 一致；并非已实测延迟结论 |

已核对候选如下，**均不是自动选定的部署模型，也不是全部可用模型的清单**。两个候选的 safetensors 索引所列 2 个分片均存在；此处只检查文件存在与元数据，不代表权重已成功加载。

| 项目 | 25 步候选 | 50 步候选 |
| --- | --- | --- |
| 权重目录（相对 L） | `output/separated_model/mixed_conditioned_chunk25/checkpoints/global_step_10000/hf_ckpt` | `output/separated_model/mixed_conditioned/checkpoints/global_step_10000/hf_ckpt` |
| checkpoint 内 `lingbotvla_cli.yaml` 的 `train.chunk_size` | 25 | 50 |
| checkpoint 内 `config.json` 的 `chunk_size` | **50（遗留值）** | 50 |
| 统计文件 | `/home/bjtc/Sophix/datasets/marked_9_1_0922_chunk25/train_stats/norm_stats.json` | `/home/bjtc/Sophix/datasets/marked_9_1_0922/train_stats/norm_stats.json` |
| 手臂动作统计形状 | `[25,14]` | `[50,14]` |
| 夹爪动作统计形状 | `[2]`，沿时间广播 | `[2]`，沿时间广播 |
| 复用模型类 | `deploy.lingbot_vla_policy_chunk25.LingbotVlaChunk25Server` | `deploy.lingbot_vla_policy.LingbotVLAServer` |

G README 中的 `output/interpolation_vla/checkpoints/global_step_10000/hf_ckpt` 和 `output/interpolation_vla_num_denoising_step_20/checkpoints/global_step_10000/hf_ckpt` 当前都不存在，不能直接拿旧命令作为可运行基线。旧统计文件仍存在，但不能因此将它配给新候选权重。

源码确认：基础类的 `use_length` 只在恢复动作数值后裁切输出，不控制训练 horizon。25 步专用类在基础加载后、`reset()` 之前将 `self.config.chunk_size` 与 `self.data_config.chunk_size` 设为 25，避免遗留 JSON 值使 FeatureTransform 使用 50。`package_a2d.yaml` 注释中写的 `[50,14]` 不是运行时限制，实际统计维度以上表文件为准。`FeatureTransform.unapply()` 已将手臂增量恢复为绝对目标，不得再次加当前状态。

已查看三个仓库的 `git status --short`：L 有未跟踪的训练配置、数据处理脚本及 tools；G 有已暂存和未暂存的文档、部署脚本等改动；O 已有 `.gitignore` 的 `/report/` 改动。本轮全部保留，不创建提交。报告目录已被忽略，本报告更新不会出现在普通 `git diff` 中。

### 4.2 动作步数的配置约定（M01/M02 实现）

只增加一个模型 horizon 参数 `chunk_size`，不将动作步数、去噪迭代次数和控制频率混为同一个参数：

| 参数 | 含义 | 约束 |
| --- | --- | --- |
| `chunk_size` | 每次模型返回的动作时间点数量 H | 首版显式支持 25 / 50；必须匹配选定权重训练 YAML |
| `num_denoising_step` | 每次采样的去噪迭代次数 | 正整数，初始拟用 10；可调，不改变 H |
| 客户端 `raw_fps` | 原始动作时间点的播放频率 | 本任务 30；不因 25 / 50 切换而变化 |

配置位于 `conf/models_conf.py` 的 LingBot ConfigDict；M02 增加命令行覆盖，优先级为显式 CLI > ConfigDict。`model_path`、`norm_path`、`chunk_size` 作为一组核对；缺失时失败，不默认取最新模型、不根据目录名猜步数。服务启动时记录最终路径、H、去噪步数和选择的模型类。切换模型时重启模型服务，先停止客户端控制并清理旧动作计划，不做运行中的热切换。

以下是候选 25 步配置示意，**尚不是可运行配置文件，也不代表已选定该权重**：

```python
cfg.repo_path = "/home/bjtc/Sophix/lingbot-vla"
cfg.model_path = cfg.repo_path + "/output/separated_model/mixed_conditioned_chunk25/checkpoints/global_step_10000/hf_ckpt"
cfg.norm_path = "/home/bjtc/Sophix/datasets/marked_9_1_0922_chunk25/train_stats/norm_stats.json"
cfg.chunk_size = 25
cfg.num_denoising_step = 10
```

M01 加载前读取 checkpoint 的 `lingbotvla_cli.yaml`，要求 `train.chunk_size == cfg.chunk_size`；按训练记录核对统计文件来源，并校验 `action.arm.position` 的统计形状为 `[H,14]`。夹爪统计 `[2]` 合法，不要求所有统计都带 H 维。形状一致只是必要条件，不能证明任意统计文件与权重匹配。使用 25 步专用类处理已知 JSON 遗留值，其他不兼容配置明确报错；`reset()` 后检查有效配置/FeatureTransform 的 chunk_size，推理后检查 `[H,16]`。不修改原 checkpoint 元数据，不补齐或裁切来掩盖错配。

M03 对 25 / 50 两条配置路径分别测试；M08 保持 `raw_fps=30`，按选定模型实测推理耗时设置等待上限；M09 关注 25 步约 0.83 秒计划下的动作供给是否连续。静态阅读 O 的动作管理、插值和衔接代码未见要求固定 50 帧的动作契约，但动态兼容性仍需 M03/M09 验证。

本轮实际修改文件：仅本报告；运行代码 0 个。下一轮为 M01，开始前需要明确实际使用的 checkpoint 及配套统计文件；无需再将 horizon 固定为 50。

## 5. M01：将 LingBot 封装为 Open-RAIL 模型

**面向来源：L。性质：适配，复用原模型计算，不改 L。**

作为依据阅读：

- `L/deploy/lingbot_vla_policy.py`、`L/deploy/lingbot_vla_policy_chunk25.py`：加载、reset、infer。
- `L/lingbotvla/data/vla_data/utils.py`：模型输出恢复的职责。
- `O/server/models/openpi/pi0.py`：现有 `ModelVLA` 输入输出形式。

实际新增或修改 3 个文件：

| 目标文件 | 操作 | 本轮职责 |
| --- | --- | --- |
| `O/server/models/lingbot_vla/lingbot_vla.py` | 新增 | 实现直接调用 LingBot 的 `ModelVLA` |
| `O/server/models/lingbot_vla/__init__.py` | 新增 | 导出 `ModelVLA` |
| `O/conf/models_conf.py` | 修改 | 新增模型枚举和 LingBot 参数配置 |

要做：

1. `ModelVLA.__init__()` 保存 `self.cfg`，按配置中的 `repo_path` 导入 L 的模型类。使用明确的源码目录，不遍历磁盘猜路径。
2. 按 `cfg.chunk_size` 选择已核对的模型类（25 / 50 显式映射），显式传 `model_path`、`robot_norm_path`、`use_length=cfg.chunk_size`、推理步数；先校验训练配置和统计形状，关闭编译选项作为初始基线。普通推理使用 `rtc_mode='off'`。
3. 调用一次 `reset('package_a2d')` 初始化输入输出变换。它不是机器人归位，不要每次请求都重新加载模型或 reset。
4. `infer(sequence)` 取单份观测，按第 2 章映射字段，并建立自己的输入字典与数组副本。LingBot 的预处理会修改传入内容，不直接修改 Open-RAIL 正在显示或记录的对象。
5. 将 `policy.infer()` 返回的 `action` 转为标准动作响应，保留原始时间字段。

核心调用关系如下。它是拟定逻辑，不是本轮已经生成的代码：

```python
# __init__ 中，实际实现还包含源码路径与配置读取
policy_cls = {25: LingbotVlaChunk25Server, 50: LingbotVLAServer}[cfg.chunk_size]
self.policy = policy_cls(
    path_to_pi_model=cfg.model_path,
    robot_norm_path=cfg.norm_path,
    use_length=cfg.chunk_size,
    num_denoising_step=cfg.num_denoising_step,
    use_compile=False,
    rtc_mode="off",
)
self.policy.reset("package_a2d")

# infer 中
response = self.policy.infer(lingbot_observation)
return {
    "type": "vla_action",
    "pred_action": response["action"],
    "ref_timestamp": data["ref_timestamp"],
    "loc_timestamp": data["loc_timestamp"],
    "ext": {},
}
```

新增模型配置以实际用到的字段为限：`repo_path`、`model_path`、`norm_path`、`chunk_size`、`num_denoising_step`。`chunk_size` 无隐式默认值，必须显式指定 25 或 50；16 维和 `package_a2d` 固定。不额外开放与之冲突的 `use_length` 配置，始终返回完整动作块。

必要检查：单份观测、所需图像与状态存在、状态顺序符合定义、输出恰为 `[cfg.chunk_size,16]` 且数值有效。不用异常值补零，也不再给手臂目标加一次当前位置。

完成标准：给一份符合约定的观测，适配器返回 Open-RAIL 标准动作字典；不创建 WebSocket 连接，不导入 G 的部署主程序。

注意：O 的 `VLAServer` 会读取 `model.cfg['model_path']`，所以 `self.cfg` 和此字段需要保留。L 的文件顶层仍有 WebSocket 相关导入，首版允许沿用原环境中的依赖；不为“去掉一种通信方式”额外重构 L 文件。

## 6. M02：接入 Open-RAIL 模型服务入口

**面向来源：L。性质：替换 L 原来启动 WebSocket 服务的方式；模型计算仍复用。**

作为依据阅读：`L/deploy/lingbot_vla_policy.py` 的 `main()`、`O/run_server.py`、`O/server/core/vla_server.py`。

实际新增或修改 2 个文件：

| 目标文件 | 操作 | 本轮职责 |
| --- | --- | --- |
| `O/run_server.py` | 修改 | 识别并实例化 LingBot，接收该模型需要的路径参数 |
| `O/scripts/run_lingbot_server.sh` | 新增 | 用模型环境启动 Open-RAIL 模型服务 |

`run_server.py` 中改三个位置，仍然只算一个文件：

1. `get_model()` 增加 LingBot 分支。
2. `--model_type` 可选值加入 `lingbot_vla`。
3. 参数覆盖逻辑支持其 `--model_path`，并增加明确的 `--repo_path`、`--norm_path`、`--chunk_size`（25 / 50）、`--num_denoising_step` 参数。新增参数仅用于所选模型，不改变已有其他模型的配置。

创建服务前，若选择 LingBot，将 `config.max_infer_workers` 设为 1。这样一个模型实例一次处理一份观测即可；不用再同时加多把锁或并发模型池。服务端默认 3 个推理工作线程不必全局修改。

启动脚本只做：定位 O、设置 `QWEN25_PATH`、使用指定的 LingBot 环境解释器，调用 `run_server.py`。模型权重与统计路径显式传入，不复制权重。

完成后的命令形式如下，**新增参数要在本轮实现后才存在**：

```text
<模型环境的 python> run_server.py
  --model_type lingbot_vla
  --repo_path /home/bjtc/Sophix/lingbot-vla
  --model_path <本次模型权重目录>
  --norm_path <对应统计文件>
  --chunk_size <25 或 50，匹配权重训练配置>
  --num_denoising_step <选定去噪步数>
```

完成标准：模型只加载一次；服务从 O 原有 ZMQ 入口收发消息。无需再运行 L 的 `python -m deploy.lingbot_vla_policy`，无需启动模型用的 8006 端口。

环境处理只要求模型 Python 能导入 O 的服务依赖。不把 GPU 模型安装进机器人 SDK 环境；依赖安装若发现具体冲突，再针对该冲突处理，不预先重建所有环境。

## 7. M03：验证模型适配 不连接机器人

**面向来源：L，以 G 既有模型输入作为参照。性质：验证 M01、M02 的适配。**

实际新增 1 个文件：

| 目标文件 | 操作 | 本轮职责 |
| --- | --- | --- |
| `O/test/test_lingbot_vla_adapter.py` | 新增 | 检查字段映射、数组含义和响应格式 |

只写能发现真实接入错误的测试：

1. 给三张不同颜色的图，确认头、左腕、右腕没有换位。
2. 给已知 20 维完整状态，确认模型收到的是顺序正确的前 16 维，夹爪没有除以 120。
3. 分别用假模型返回已知的 25×16 和 50×16 数组，确认选择对应模型类、传入对应 `use_length`，且没有转置、重复恢复数值或修改时间字段。
4. 确认创建时进行了 `reset('package_a2d')`；一次推理没有重新加载或 reset。
5. 错误输出维度、配置与训练 horizon 不一致、错配的统计文件均明确报错，不悄悄补零或截取。覆盖 25 步权重 `config.json` 遗留 50、训练 YAML 为 25 的专用加载路径，并检查 reset 后有效 chunk_size。

然后在模型环境中，用一份保存的真实观测做一次推理，确认真实权重、统计文件和 `package_a2d` 可共同工作，并记录实际耗时。该调用不连接机器人 SDK。

完成标准：接口测试通过，选定的真实模型返回有效的 H×16 动作（H 与配置一致）；另一种步数若只跑了假模型测试，需明确尚未完成其真实推理验证。此时证明的是“模型已接入”，还不宣称真机迁移完成。

### M03 执行记录（2026-10-03）

- 新增 `test/test_lingbot_vla_adapter.py`：覆盖 25 / 50 步加载选择、相机与状态映射、输入副本、动作与时间字段，以及必要的错配检查。
- 模型环境运行结果：**26 passed, 1 skipped**。默认测试仅使用假模型和临时数据，不占用 GPU。
- 真实观测测试入口已提供，需显式设置 `LINGBOT_TEST_*` 环境变量；使用 G 保存的观测，不连接机器人 SDK。参数说明见测试文件开头。
- 按用户要求暂缓真实模型加载与 GPU 推理，避免影响主机上的训练；未测量真实推理耗时。
- 状态：**接口验证完成，M03 真实推理验收待执行**。本轮未选定或加载任何 checkpoint。

## 8. M04：用 Open-RAIL 替换 G 的客户端启动入口

**面向来源：G。性质：复用机器环境，替换部署入口。**

作为依据阅读：`G/g1_pc_gdk_env.sh`、`G/README.md` 的机器准备流程、`O/run_web_client.py`。

实际新增 2 个文件：

| 目标文件 | 操作 | 本轮职责 |
| --- | --- | --- |
| `O/scripts/run_lingbot_g1_client.sh` | 新增 | 准备 GDK 环境并启动 O 的网页客户端 |
| `O/server/models/lingbot_vla/README.md` | 新增 | 记录模型端与机器人端的两个环境、启动命令和依赖 |

要做：

1. 按用户追加要求，改为 `source O/scripts/g1_pc_gdk_env.sh`，激活 O 的 `.venv`，保留当前机器的 locator、发现地址、时钟模式及厂家 SDK 环境。
2. 切到 O 根目录，通过 `run_web_client.py --conf lingbot_package.yaml` 启动；M08 创建该任务配置后，完整启动命令才成立。
3. 确认启动 Web 客户端的解释器能够同时导入 O 和厂家 SDK。RobotProxy 的子进程不会自动换到另一个虚拟环境。
4. COPILOT 模式切换由追加迁移块 M04a 迁入 O，使用独立入口；网页启动脚本不自动切机器模式或自动执行动作。

完成标准：启动网页后能创建 O 客户端所需组件，模型端与 SDK 端环境互不混淆。G 的旧控制脚本不同时运行。

客户端已不再依赖 G 的环境准备脚本或虚拟环境。`O/scripts/setup_g1_env.sh` 使用 uv 创建 O 的 Python 3.10 `.venv` 并安装本项目和 SDK wheel；仍引用厂家安装目录中的 wheel 与底层 `env.sh`，不复制厂家运行文件。M00 表中的旧 GDK 解释器路径作为核对时的历史记录保留。

### M04 执行记录（2026-10-03）

- 新增 `scripts/run_lingbot_g1_client.sh`：固定软包配置；M08 配置缺失时停止。后按用户追加要求，改为调用 O 的本地环境脚本及 `.venv/bin/python`。
- 新增 `server/models/lingbot_vla/README.md`：说明两套环境、依赖、启动命令和当前验证边界。
- GDK 环境按现有版本约束补齐客户端依赖，原有包版本未改变；网页应用、客户端和 SDK 可在同一解释器导入，`--help` 通过。
- 脚本语法与临时环境下的参数传递、失败退出检查通过。未执行真实 GDK 环境脚本，未启动网页、模型或机器人实例。
- 追加环境迁移：`scripts/g1_pc_gdk_env.sh` 管理本地环境和网络参数；`scripts/setup_g1_env.sh` 用 uv 安装客户端依赖。模型服务继续使用原 LingBot 环境，避免干扰训练。
- 本地 `.venv` 已创建（Python 3.10.12），uv 检查 47 个包依赖兼容；Web 应用、VLAClient、RobotProxy、RobotBody、SDK 导入及网页入口 `--help` 通过。已验证本地环境脚本的参数传递与失败退出，未执行真实厂家环境脚本或机器人控制。
- 状态：**启动脚本与环境准备完成；完整网页及真机组件创建验收待 M08 配置和后续适配完成**。

### M04a：COPILOT 模式切换入口（已迁移，2026-10-03）

**来源：G 的 `g1_enter_copilot.sh`。性质：迁移机器准备功能，不修改模型或动作调度。**

本轮修改 3 个文件：

| 文件 | 改动 |
| --- | --- |
| `O/scripts/g1_enter_copilot.sh` | 新增模式切换入口，保留原脚本检查、切换顺序和确认参数 |
| `O/README-LingBot-G1.md` | 真机启动步骤改用本仓库入口，说明外部运行资源路径 |
| 本报告 | 记录追加迁移范围与验证结果 |

脚本默认通过 SSH 只读检查 Orin 的模式服务。显式执行时，加载 O 的 `scripts/g1_pc_gdk_env.sh`，使用 O 的 `.venv/bin/python` 调用厂家 `robot_service`，依次切换 idle、COPILOT，再检查组件与 PC forwarder 的反馈。执行命令：

```bash
cd /home/bjtc/Sophix/g1-open-rail
scripts/g1_enter_copilot.sh
scripts/g1_enter_copilot.sh --execute --confirm SWITCH_FROM_VR_TO_COPILOT
```

第二条才会切换模式，两条命令本次均未对真机运行。厂家目录与 SSH 密钥仍引用 G 的现有资源，可用 `GDK_DIR`、`ORIN_KEY` 覆盖。密钥不复制；旧 G 入口保留，以免影响原部署。Orin 常驻模式服务的安装修复工具尚未迁移，错误提示仍指向原修复工具。

验证结果：`bash -n` 语法检查通过；在临时副本中用本地替代命令隔离 SSH、SDK、ROS 和等待，验证只读检查、正确确认后的 idle→COPILOT 顺序、错误确认拒绝、模式服务未启动拒绝，4 项全部通过。确认新入口调用 O 本地环境与 Python，并支持从其他工作目录启动。未连接机器人，未运行真实厂家环境脚本或模式切换；真机效果仍待现场验证。

### M04b：PC forwarder 启停入口（2026-10-03）

**来源：`G/vendor_packages/a2d_sdk-1.5.0/scripts/ros_env_wrapper.sh`。性质：迁移通信桥的操作入口，复用厂家二进制和库。**

本轮修改 3 个文件：`O/scripts/ros_env_wrapper.sh`、`O/README-LingBot-G1.md`、本报告。

在 Open-RAIL 根目录运行：

```bash
scripts/ros_env_wrapper.sh start
```

脚本先检查是否已有 forwarder，再加载其运行库和 O 的 `scripts/g1_pc_gdk_env.sh`，最后前台启动厂家桥接程序。O 环境脚本最后按机器人路由确定网络地址，避免被厂家环境覆盖。无需另外 source，也不再调用旧目录的启动脚本。

结束自动控制后，使用 `scripts/ros_env_wrapper.sh stop` 停止桥接。它沿用原工具的精确进程路径匹配和强制终止行为，不匹配同目录的 ROS 命令行工具。此入口不负责切 COPILOT，也不启动模型或网页。

厂家目录默认仍为相邻 `g1/vendor_packages/a2d_sdk-1.5.0`，允许 `GDK_DIR` 覆盖。不复制厂家运行文件；迁移的是启停逻辑与操作路径。

验证结果：`bash -n` 通过。临时环境替代真实进程命令、厂家环境和二进制，启动、已有实例、停止、无效参数、缺失参数、环境加载失败共 6 项检查通过；确认网络参数最后由 O 环境确定，支持从其他工作目录启动。未执行真实厂家环境，未启动或停止真实通信桥。

## 9. M05：对齐三路图像和机器人状态

**面向来源：G 的 `read_observation()` 与 `_rgb_frame()`。性质：适配输入含义，保留 O 的采集方式。**

作为依据阅读：

- `G/运控test/g1_native_vla_deploy.py`：状态与图像的含义。
- `O/client/robots/agibot_g1/body_robot.py`：按头相机参考时间获取其他观测。
- 本机 SDK 的相机解码接口：明确返回的是 RGB 还是 BGR。

实际改动最多 3 个文件：

| 目标文件 | 操作 | 本轮职责 |
| --- | --- | --- |
| `O/client/robots/agibot_g1/body_robot.py` | 按差异修改 | 保持模型状态原始值，明确给图像编码器的颜色格式 |
| `O/conf/robots_conf.py` | 仅有实际需要时修改 | 定义新增机器人输入设置；已有字段直接沿用 |
| `O/test/test_lingbot_g1_observation.py` | 新增 | 验证相机顺序、颜色和状态排列 |

要做：

1. 保留 O 的“以头图像时间为参考，找最近的腕图像与状态”的读取方法，不把 G 的顺序取最新值循环整段搬入。
2. 保持读取顺序 `arm, gripper, head, waist`。模型输入来自 `obs.state`；界面显示用的归一化状态不能替代它。
3. 核对整条颜色路径，而不是把 G 的 RGB 返回值直接塞到 O 的 OpenCV 编码位置。

M05 实现后的图像路径为：

```text
SDK 读取同一个图像包（图像、格式与时间戳）
  → RobotBody 按该包的编码/颜色格式解码为 BGR，供 OpenCV 编码
  → O 服务端解码得到 BGR，再转为 RGB
  → LingBot 适配器收到 RGB
```

当前代码对压缩图像可能已经符合这一流程，验证正确就不改。未压缩图像若因 SDK 的颜色格式不同而不一致，只在 RobotBody 内按实际数据包格式转换；按最近时间读取时，使用对应帧的格式信息，不拿另一帧的“最新包”解释它。

保留 O 的 JPEG 传输。L 继续执行原来的模型图像预处理；额外缩放由 M08 关闭。不为这轮迁移加入 PNG 协议、图像版本协商或新的采集系统。

完成标准：在模型入口看到正确的三路图像；给定一组已知反馈，模型前 14 维是双臂角度，最后两维仍是原始夹爪反馈。正确的已有代码允许零修改，测试结果就是这一轮的产物。

### M05 执行记录（2026-10-03）

- 修改 `client/robots/agibot_g1/body_robot.py`：从同一数据包解码图像，修正未压缩 RGB 通道交换；保留头图像参考时间和最近腕图像/状态读取。
- 状态改为按顺序拼接，修复原缓冲区首次扩容时丢失前面已写入关节值的问题；模型使用原始夹爪反馈，显示归一化只作用于 `current_state`。
- 观测完整读取成功后再更新去重时间戳，缺帧时不提前消耗该参考帧。
- 新增 `test/test_lingbot_g1_observation.py`：9 项离线测试通过，覆盖压缩/原始 RGB/BGR、首帧状态、最近时间对齐、JPEG 到模型入口、重复帧及缺帧处理。现有 `conf/robots_conf.py` 无需修改。
- 合并 M03 测试结果为 **35 passed, 1 skipped**；Python 语法及 Git 差异检查通过。未导入真实 SDK、未加载 GPU 模型、未连接机器人，真机采集验收仍待后续执行。

## 10. M06：适配双臂和夹爪的实际执行

**面向来源：G 的 `execute_prefix()` 与执行前状态检查。性质：迁移任务规则，不迁移循环和 sleep。**

作为依据阅读：`G/运控test/g1_native_vla_deploy.py` 中的 `_fresh()`、`_status_is_safe()`、`_check_live_status()`、`execute_prefix()`。

实际新增或修改 2 个代码／测试文件，另同步 README：

| 目标文件 | 操作 | 本轮职责 |
| --- | --- | --- |
| `O/client/robots/agibot_g1/body_robot.py` | 修改 | 双臂绝对目标、左夹爪保持、右夹爪四次方处理及执行前状态检查 |
| `O/test/test_lingbot_g1_control.py` | 新增 | 用假 SDK 检查命令、采样与异常阻断 |

按用户确认，不保留旧夹爪模式，不新增 `gripper_command_mode`，直接采用以下规则：

- 双臂：将 14 个绝对目标角度交给 `move_arm()`。
- 右夹爪：令 `x=clip(action[15], 0, 1)`，发送 `x**4 / (x**4 + (1-x)**4)`；保留原 `gripper_freq` 发送间隔。
- 左夹爪：发送执行前采样的 `clip(raw/120, 0, 1)`，不参与四次方处理，不采用模型左夹爪目标。
- 发命令前：检查关节／整机状态时间戳（0.5 秒）、14 维有效关节反馈、故障、急停及双臂控制状态。
- 自动执行只接受 16 维有效动作，不发送头、腰或底盘命令；手动 `execute_action()` 保持原样。

新增 `prepare_policy_control()`，只检查状态、采样左夹爪保持值和重置发送计数，不发送运动命令。准备失败会清除旧保持值。未准备时，`control_robot()` 明确报错。

M07 在每次开始／恢复自动执行时调用准备接口，连续执行期间保持左夹爪。旧 G 每轮重新采样，此处适配为开始／恢复采样；M06 测试直接调用接口，启停流程由 M07 接入。

**执行结果：**新增 36 项假 SDK 测试，覆盖左夹爪保持／重新采样、右夹爪曲线与裁剪、发送间隔、状态异常阻断、原数组不被修改和手动入口。右目标 `0.3` 实际发送约 `0.032635`。连同 M03/M05 共 **71 passed, 1 skipped**；未加载真实模型或连接机器人。

## 11. M07：把左夹爪保持值接到控制开始时刻

**面向来源：G 的“执行前读取左夹爪保持值”。性质：适配到 O 已有启停流程。**

实际修改 2 个文件：

| 目标文件 | 操作 | 本轮职责 |
| --- | --- | --- |
| `O/client/core/vla_client.py` | 修改 | 在从停止变为执行时调用准备方法 |
| `O/test/test_lingbot_g1_control.py` | 继续修改 | 验证首次执行与恢复时重新采样 |

已实现：

1. 在 `start_control()` 真正启用控制前，若机器人提供 `prepare_policy_control()`，先调用它。
2. 只在“未执行 → 执行”时调用；已经运行时重复点击开始，不反复改保持值。
3. 准备完成后，继续使用原来的 `resume_controls()`、控制线程和暂停机制；失败则不启用控制。
4. 暂停后由人调整左夹爪，再恢复执行时，重新读取当前保持值。

不用为此改 RobotProxy：它已有收集机器人方法并通过 `__getattr__()` 转发调用的机制，新增的 RobotBody 方法可沿现有通道在 SDK 工作进程里执行。

完成标准：仅观察、仅推理时不发送运动命令；开始执行前得到保持值；恢复后采用新的保持值；已有其他机器人没有此方法时仍按原流程运行。

这一轮是一个准备动作的调用点，不是重写暂停、重新实现队列清理或添加新的控制权状态机。

依据：[现有控制启用入口](../client/core/vla_client.py:189)、[机器人方法收集](../client/robots/robot_proxy.py:155)、[已有方法转发](../client/robots/robot_proxy.py:681)。

**执行结果：**`start_control()` 在原控制锁内先准备、再恢复代理控制，已经执行时直接返回。新增 6 项测试，覆盖首次开始、重复开始、暂停恢复、准备失败后重试、仅观察／推理、无准备接口的其他机器人。连同 M03～M06 与现有暂停／代理异步控制测试，共 **82 passed, 1 skipped**。未加载真实模型或连接机器人。

## 12. M08：写入软包任务配置 复用异步执行与记录

**面向来源：G 的部署参数 + L 的输入输出定义。性质：用 O 配置替换旧脚本参数。**

实际新增 2 个文件：

| 目标文件 | 操作 | 本轮职责 |
| --- | --- | --- |
| `O/conf/lingbot_package.yaml` | 新增 | 设置机器人、动作处理、通信等待和记录格式 |
| `O/conf/lingbot_package_language.json` | 新增 | 保存软包任务文字 |

配置应明确下列选择，不依赖本地 `default_conf.yaml` 的泡茶任务设置：

| 设置 | 初始选择 | 为什么这样设置 |
| --- | --- | --- |
| 机器人 | `agibot_g1`，三路相机沿用现有名称 | 使用 O 现有 G1 适配 |
| 模型时间间隔 | `raw_fps=30`、`speed=1.0` | H=25 / 50 时名义覆盖约 0.83 / 1.67 秒计划；切换 H 不改变 30Hz 播放频率 |
| 请求下一段 | `rdm.mode=async` | 旧计划执行期间计算新计划，直接复用 O |
| 一段动作内部 | `intra_chunk_mode=interpolation` | 使用已有插值补充中间位置；该分支对夹爪保持前一个值，避开拟合分支的夹爪平均处理 |
| 两段衔接 | `inter_chunk_mode=min_jerk` | 使用已有过渡处理，避免另写桥接算法 |
| 控制取点周期 | 先沿用 O 的 `period=3.75` 毫秒 | 与加密后的曲线点配套；它不是模型每 3.75 毫秒推理一次 |
| 夹爪时间偏移 | `gripper_offset=0` | 不额外提前或延后开合 |
| 夹爪发送间隔 | 初始可设 `gripper_freq=9`，再核对实际调用 | 名义每 9 次、每次 3.75 毫秒，约 33.75 毫秒发一次；不是 9Hz，也不保证真实到达频率 |
| 历史图像 | `history_frame=false` | 一次使用当前的一份多相机观测 |
| 客户端额外缩放 | `vision.preprocess.method=none` | 让 L 继续负责训练时的图像尺寸处理；O 原有 JPEG 传输保留 |
| 模型等待上限 | 暂设 `vla_zmq.infer_timeout=10000` 毫秒 | 未运行真实推理，待实测调整；现有客户端首次请求使用 4 倍超时 |
| 任务 | 新 JSON 中的 `package_a2d`，关闭自动换子任务 | 当前只执行软包任务 |
| 记录 | 状态 20 维、动作 16 维，单独保存目录 | 复用 O 记录器，不把动作补成 22 维后当成模型输出 |

以上控制与夹爪周期是验证起点，不是已完成实机测量的结论。RobotProxy 可能合并目标，`gripper_freq` 按实际机器人控制调用计数，所以必须看实际开合是否及时。

这里使用插值的原因是：O 已经有一条能够补充手臂中间位置、又不对夹爪做窗口平均的分支，配置就能复用，不必修改 `intra_chunk_smoother.py`。插值仍会改变中间路径，不能保证不会超出原目标范围，M09 应对照实际轨迹。

如果另外想观察不经插值的原始动作，再做 `raw` 对照，并把控制周期同时改成约 33.33 毫秒。不能只改为 `raw` 却继续每 3.75 毫秒取下一个原始目标，那会把计划过快播放。正式迁移不以复刻旧串行循环为目标。

任务 JSON 的内容：

```json
{
  "package_a2d": [
    "Pick a soft package from the box, orient its label upward, and place it on the conveyor belt."
  ]
}
```

完成标准：网页加载该配置后显示软包任务，使用 O 的异步执行；记录形状与本任务一致。M06 直接使用已确认的夹爪规则，不需要额外模式字段。

依据：[现有动作配置](../conf/client_conf.py)、[插值分支](../client/core/intra_chunk_smoother.py:432)、[YAML 读取](../web_client/server.py:1134)、[记录形状配置](../conf/save_conf.py)。

**执行结果：**新增上述 YAML 和 JSON；`.gitignore` 单独放行此任务 YAML，以便纳入版本管理，README 同步运行说明。默认关闭记录，目录为 `data/lingbot_package`。本地 `.venv` 通过真实 Web YAML 加载器逐项核验、任务文字读取及 20／16 维检查；25／50 步假动作经现有插值器后仍为 16 维，夹爪保持前值，控制点间隔为 3.75 毫秒。未创建真实机器人、启动网页服务或加载模型；完整网页与真机验收留到 M09。

## 13. M09：从观测到真机执行完成闭环验收

**面向来源：L + G。性质：确认模型功能与机器人功能在 O 中共同工作。**

实际修改 1 个文件：

| 目标文件 | 操作 | 本轮职责 |
| --- | --- | --- |
| `O/server/models/lingbot_vla/README.md` | 更新 | 写入经过验证的启动命令、所用模型与配置、实际结果 |

本轮原则上不改运行核心代码。遇到明确失败，回到对应迁移块修复，不把所有模块一起改。

按以下顺序验收：

### 13.1 启动与观测

- 按现有 G 流程准备机器，启动 O 的 LingBot 模型服务和网页客户端。
- 在网页打开观测，确认头、左右腕画面与关节反馈。
- 用的是当前真实反馈，不是 mock 数据或旧图片。

### 13.2 只做推理

- 通过 O 已有的独立启停接口开启推理，保持控制未开启；不直接把整体 Start 当成旧 G 默认 dry-run。
- 模型返回 H×16（H 与选定权重和配置一致），任务文本正确，三路图像没有交换。
- 首次加载、首次推理和后续推理耗时分别记录，不把加载权重时间混入正常推理时间。

### 13.3 执行短段动作

- 在现场原有操作流程下开启控制，确认左夹爪保持、右夹爪跟随任务，双臂运动方向正确。
- 确认只有 O 在发送模型控制目标，不同时运行旧 G 部署入口。
- 先观察短段，再验证完整软包任务；关注新旧动作切换处是否发生不合理变化。

### 13.4 暂停与恢复

- 用现有网页暂停，确认旧目标不再继续由客户端提交。
- 暂停后调整左夹爪，恢复时 M07 重新取得保持值。
- 记录当前机器停止接收新目标后的实际表现。复用客户端暂停，不将它直接等同于厂家硬件急停。

### 13.5 记录与重复运行

- 开启现有记录功能，确认图像、状态和处理后动作写入本任务目录，维度正确。
- 记录器保存的是处理后、提交给机器人代理的目标。不要把它命名成“硬件确认收到的动作”；左夹爪在执行侧替换、右夹爪在执行侧做四次方处理，所以它也不自动等于最终 SDK 参数。
- 本次不扩展 SDK 级逐次记录。M06 已用假 SDK 验证命令替换；若以后要精确诊断实际发送时间，再单独做该需求。
- 重复执行一次，确认模型不重复加载、暂停恢复正常、记录没有混进上一任务。

最终完成标准：

```text
L 的同一个模型能通过 O 加载并推理
模型输入仍符合 package_a2d 定义
G 的软包夹爪规则在 O 的执行侧成立
O 的采集、异步、过渡、暂停、记录实际可用
网页能观察真实 G1，并完成软包任务闭环
```

没有实机结果时，应将状态写成“代码接入完成，真机验收未完成”，不能用一次数组输出代替完整迁移结论。

## 14. 本次保持复用的核心模块

| Open-RAIL 文件 | 为什么不用为了接 LingBot 就修改 |
| --- | --- |
| `server/core/vla_server.py` | 已经能解码图像、调用 `model.infer()` 并返回标准响应；M01 实现它要求的接口 |
| `client/core/zmq_client.py`、`server/core/zmq_server.py` | 原有模型通信足够使用，不增加第二段模型 WebSocket |
| `client/core/realtime_data_manager.py` | 已有存储、取点、选取新计划起点的功能，不复制旧 g1 调度 |
| `client/utils/multi_thread_timer.py` | 已有独立发送定时器，按配置运行 |
| `client/core/intra_chunk_smoother.py` | 已有插值分支，通过 M08 选择 |
| `client/core/inter_chunk_fuser.py` | 已有新旧动作衔接，通过 M08 选择 |
| `client/robots/robot_proxy.py` | 已有 SDK 子进程、暂停队列处理和机器人方法转发，足够支持 M07 |
| `client/core/data_record_manager.py`、`client/core/lerobot_dataset_recorder.py` | 已有记录机制，通过任务配置设置形状和目录 |
| `web_client/server.py` 与前端 | 已有配置、观测、推理、控制和记录入口；本次不另做操作面板 |

`vla_client.py` 在 M07 仅加入执行开始前的准备调用，不改变异步推理算法、超时等待和暂停实现。

复用不表示这些模块没有任何可改进之处。只是**通用框架优化不是接入 LingBot 的前置任务**；真机验证中出现具体问题，再定位具体位置。

## 15. 交付清单与逐轮执行方式

新增文件：

```text
server/models/lingbot_vla/lingbot_vla.py
server/models/lingbot_vla/__init__.py
server/models/lingbot_vla/README.md
scripts/run_lingbot_server.sh
scripts/run_lingbot_g1_client.sh
scripts/g1_enter_copilot.sh
scripts/ros_env_wrapper.sh
conf/lingbot_package.yaml
conf/lingbot_package_language.json
test/test_lingbot_vla_adapter.py
test/test_lingbot_g1_observation.py
test/test_lingbot_g1_control.py
```

现有文件修改集中在：

```text
conf/models_conf.py
run_server.py
conf/robots_conf.py
client/robots/agibot_g1/body_robot.py
client/core/vla_client.py
```

不要求改动 L 的模型实现和 G 的旧部署入口。模式切换、环境准备和客户端启动均从 O 的 `scripts/` 进入；运行时仍引用 L 模型源码和模型环境、厂家的底层 SDK 运行目录及现有 SSH 密钥。客户端 Python 环境为 O 自己的 `.venv`。软包归位与 Orin 模式服务安装修复工具尚未迁入。

每轮结束时按同一个简短格式记录：

```text
轮次：Mxx
来源：lingbot-vla / g1 / 两者
本轮完成的功能：……
实际修改文件：逐个列出，最多 3 个
验证结果：……
尚未完成：……
下一轮：Mxx
```

这份清单的执行目标是：每次只解决一个可以解释和验证的接入问题，最终由 Open-RAIL 完成真机闭环，而不是逐文件复制旧仓库。

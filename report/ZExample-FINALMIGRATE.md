# TRAIN_E1Lab / CTRL_E1Base 迁移到 N2 的最终执行清单

## 0. 文档目标

这份文档只回答一个问题：接下来为了把当前 E1 训练和部署体系迁移到 N2，需要按什么顺序、拆成哪些功能块去改代码。

迁移原则：

1. 不做临时 flat/fallback task，不以“最小可运行”为目标，而是保持当前 E1 体系的功能一致性。
2. N2 与 E1 必须包级、命名级、配置级解耦。N2 不应放进 `NoetixE1` 命名空间，也不应复用 E1 hardcode。
3. TRAIN 侧和 CTRL 侧通过固定接口协议对齐：joint order、action scale、default joint pos、PD 参数、ONNX input/output shape、metadata、motion 格式。
4. 训练链路按 E1 现有逻辑 1:1 迁移：
   - Mimic 使用 `HimOnPolicyRunner` / `HIMPPO`。
   - WalkRun AMP 使用 `AmpHimOnPolicyRunner` / `AMPHIMPPO`。
5. N2 motion 未到位时，Mimic 和 AMP 不能完整训练或 play，这是预期状态；代码迁移可以先完成，运行验证等 motion 到位后再做。

## 1. 总迁移路线

```text
P0: 固定接口协议
  -> P1: TRAIN 侧 NoetixN2 包、资产、task、runner、motion 接口补齐
  -> P2: TRAIN 侧 play / ONNX export / sim2sim 迁移
  -> P3: 训练 N2 policy 并导出 ONNX
  -> P4: CTRL 侧 N2 Gazebo description、launch、controller config、policy 接入
  -> P5: CTRL 侧 controller 解耦与 N2 walk / mimic / dance 控制
  -> P6: Gazebo sim 验证
  -> P7: 真机硬件接口迁移，需额外硬件拓扑信息
```

当前最重要的主线：

```text
N2 软件标准 joint order
  = source/NoetixN2/NoetixN2/assets/robots/n2/n2.py 中的 N2_10DOF_JOINT_NAMES / N2_18DOF_JOINT_NAMES
  = TRAIN action order
  = ONNX metadata joint_names
  = CTRL policy_joint_names
  = Gazebo controller policy order
```

真机 motor / EtherCAT / CAN / SDK 顺序是另一层硬件映射，不能和软件 policy joint order 混为一谈。

## 2. 迁移块总表

| 编号 | 迁移块 | 仓库 | 目标 | 主要产物 |
|---|---|---|---|---|
| M00 | 分支和基线整理 | TRAIN / CTRL | 保证后续 diff 可追踪 | 当前分支、基线 commit、迁移分支 |
| M01 | N2 接口协议源头 | TRAIN | 固定 N2 joint/action/metadata 标准 | `n2.py`、接口检查逻辑 |
| M02 | TRAIN NoetixN2 包级解耦 | TRAIN | N2 task 不依赖 E1 package | `source/NoetixN2` |
| M03 | N2 robot asset 与 body 命名确认 | TRAIN | 固定 URDF/MJCF/body/contact/IMU 资产 | `assets/robots/n2` |
| M04 | N2 motion 数据目录与格式契约 | TRAIN | 为 Mimic/AMP 数据到位做准备 | `assets/datasets/.../n2_*` |
| M05 | `Mimic-N2-18DOF` 迁移 | TRAIN | 1:1 迁移 E1 Mimic 链路 | Mimic env/cfg/agent/mdp |
| M06 | `WalkRun-N2-AMP-10DOF` 迁移 | TRAIN | 1:1 迁移 10DOF AMP 走跑 | WalkRun 10DOF env/cfg/agent/mdp |
| M07 | `WalkRun-N2-AMP-18DOF` 迁移 | TRAIN | 1:1 迁移 18DOF AMP 走跑 | WalkRun 18DOF env/cfg/agent/mdp |
| M08 | AMP motion loader 中性化 | TRAIN / RSL-RL | 去除 `MotionLoaderE1` 歧义 | `AmpJsonMotionLoader` |
| M09 | TRAIN play / ONNX export 迁移 | TRAIN | N2 checkpoint 可导出带 metadata 的 ONNX | `scripts/rsl_rl/play.py` |
| M10 | TRAIN sim2sim 入口迁移 | TRAIN | N2 ONNX 可在 sim2sim 验证 | `scripts/sim2sim/*n2*` |
| M11 | CTRL N2 description / Gazebo 资产 | CTRL | Gazebo 能加载 N2 robot | `legged_n2_description`、`n2_empty_world.launch` |
| M12 | CTRL N2 controller yaml | CTRL | 控制器维度、joint order、policy 路径对齐 ONNX | `n2_*dof_ac.yaml` |
| M13 | CTRL controller 代码解耦 | CTRL | 去除 E1-only hardcode，支持 N2 | N2 controller 或 robot profile |
| M14 | CTRL N2 Gazebo 启动链路 | CTRL | 一条命令启动 N2 Gazebo policy 控制 | `simulation_n2_*.sh` |
| M15 | CTRL N2 mimic / dance 链路 | CTRL | 对齐 Mimic/Dance policy 和 motion | N2 motion/policy/config |
| M16 | CTRL N2 真机硬件接口 | CTRL | 真机部署，依赖硬件信息 | `legged_n2_hw` |
| M17 | 分层验证与交付清单 | TRAIN / CTRL | 每个阶段可验收 | 验证命令、日志、ONNX、报告 |

## 3. M00: 分支和基线整理

目标：保证后续所有迁移改动都能被追踪、回滚和 review。

要做：

1. 在 `TRAIN_E1Lab` 和 `CTRL_E1Base` 各自确认当前分支、远端和未提交改动。
2. 新建迁移分支，例如：
   - TRAIN: `feature/n2-train-migration`
   - CTRL: `feature/n2-control-migration`
3. 保留 E1 当前可运行链路，不在 E1 原配置里直接覆盖 N2。
4. 每完成一个迁移块，至少保证能看到清晰 diff；是否 commit 由项目节奏决定。

完成标准：

1. E1 原 task、脚本、配置仍然存在。
2. N2 改动集中在 N2 命名空间或明确的公共工具中。
3. 后续所有修改都能通过迁移块编号追溯。

## 4. M01: N2 接口协议源头

目标：先固定 N2 软件层协议，避免后面 TRAIN、ONNX、CTRL 各写一套顺序。

主要文件：

```text
TRAIN_E1Lab/source/NoetixN2/NoetixN2/assets/robots/n2/n2.py
TRAIN_E1Lab/report/7-7-interface.md
```

要做：

1. 以 `n2.py` 中的 `N2_10DOF_JOINT_NAMES` 和 `N2_18DOF_JOINT_NAMES` 作为 N2 软件标准顺序。
2. 确认 `N2_10DOF_ACTION_SCALE`、`N2_18DOF_ACTION_SCALE` 从 robot cfg 生成，并且顺序与 joint names 一致。
3. 明确 N2 policy 的 action 公式：

```text
target_joint_pos = default_joint_pos + action_scale * policy_action
```

4. 明确 ONNX metadata 必须包含：

```text
joint_names
default_joint_pos
action_scale
joint_stiffness
joint_damping
```

5. 在后续 TRAIN play、CTRL yaml、CTRL controller 中都以这五个字段做边界检查。

完成标准：

1. N2 所有训练 task 的 action order 都显式来自 `N2_*DOF_JOINT_NAMES`。
2. CTRL 侧 `policy_joint_names` 准备完全复制这个顺序，而不是使用 E1 简写名或 E1 alias map。
3. 如果某个环节必须换顺序，只能通过明确 wrapper 或 mapping 做转换，并写明输入顺序和输出顺序。

## 5. M02: TRAIN NoetixN2 包级解耦

目标：N2 训练代码独立存在，不反向依赖 `NoetixE1`。

主要文件：

```text
TRAIN_E1Lab/source/NoetixN2/pyproject.toml
TRAIN_E1Lab/source/NoetixN2/setup.py
TRAIN_E1Lab/source/NoetixN2/config/extension.toml
TRAIN_E1Lab/source/NoetixN2/NoetixN2/__init__.py
TRAIN_E1Lab/source/NoetixN2/NoetixN2/tasks/__init__.py
TRAIN_E1Lab/source/NoetixN2/NoetixN2/assets/__init__.py
TRAIN_E1Lab/source/NoetixN2/NoetixN2/managers/
TRAIN_E1Lab/source/NoetixN2/NoetixN2/terrains/
```

要做：

1. 保持 `source/NoetixN2` 作为独立 Isaac Lab extension。
2. `NoetixN2.tasks.__init__` 负责自动导入 N2 task 子包。
3. `scripts/rsl_rl/train.py`、`scripts/rsl_rl/play.py`、`scripts/list_envs.py` 需要能 import `NoetixN2.tasks`。
4. 检查 N2 代码中是否还有不合理的 `NoetixE1.*` import。如果是共享逻辑，有两种处理方式：
   - 复制到 `NoetixN2`，保持解耦。
   - 新建无机器人语义的公共模块，例如 `NoetixCommon`，但只有在 E1/N2 确认都能复用时才做。
5. 清理不应纳入源码的 `__pycache__`，避免把运行产物当成迁移内容。

完成标准：

1. `NoetixN2` 可被 Python import。
2. `WalkRun-N2-AMP-10DOF`、`WalkRun-N2-AMP-18DOF`、`Mimic-N2-18DOF` 能被 task registry 发现。
3. N2 task 不需要通过 `NoetixE1.tasks.*` 才能运行。

## 6. M03: N2 robot asset 与 body 命名确认

目标：固定 N2 在 Isaac Lab、sim2sim、Gazebo 中共用的 robot 模型和关键 body 名称。

主要文件：

```text
TRAIN_E1Lab/source/NoetixN2/NoetixN2/assets/robots/n2/n2.py
TRAIN_E1Lab/source/NoetixN2/NoetixN2/assets/robots/n2/urdf/n2.urdf
TRAIN_E1Lab/source/NoetixN2/NoetixN2/assets/robots/n2/urdf/n2_10dof.urdf
TRAIN_E1Lab/source/NoetixN2/NoetixN2/assets/robots/n2/mjcf/n2_18dof.xml
TRAIN_E1Lab/source/NoetixN2/NoetixN2/assets/robots/n2/mjcf/n2_10dof.xml
TRAIN_E1Lab/source/NoetixN2/NoetixN2/assets/robots/n2/meshes/
```

要做：

1. 确认 18DOF URDF 与 10DOF URDF 的 actuated joints 正确。
2. 确认 foot/contact body 名：

```text
L_leg_ankle_link
R_leg_ankle_link
```

3. 确认 base/root body 名。N2 没有 E1 的 waist body，不能继续使用 `waist_yaw_link` 作为通用 anchor。
4. 确认 Mimic body_names、AMP key bodies、terrain contact bodies 使用 N2 真实 link 名。
5. 为后续 CTRL Gazebo 准备 URDF 的 transmission、gazebo plugin、IMU frame、contact link 信息。如果 TRAIN URDF 缺少 Gazebo 所需标签，CTRL 侧需要生成部署版 URDF。

完成标准：

1. N2 train cfg 中没有 E1 body name。
2. 10DOF 和 18DOF 的 action joint 数量与 `N2_*DOF_JOINT_NAMES` 一致。
3. CTRL 侧可根据同一套 joint/link 名生成 N2 Gazebo description。

## 7. M04: N2 motion 数据目录与格式契约

目标：即使 motion 文件未到位，也先固定目录、格式和检查规则。

主要目录：

```text
TRAIN_E1Lab/source/NoetixN2/NoetixN2/assets/datasets/mimic/n2_18dof/
TRAIN_E1Lab/source/NoetixN2/NoetixN2/assets/datasets/walkrun/n2_10dof/
TRAIN_E1Lab/source/NoetixN2/NoetixN2/assets/datasets/walkrun/n2_18dof/
```

Mimic `.npz` 必须至少包含：

```text
fps
joint_pos
joint_vel
body_pos_w
body_quat_w
body_lin_vel_w
body_ang_vel_w
```

AMP JSON 必须包含：

```text
FrameDuration
JointNames
KeyPosNames
MotionWeight
Frames
```

要做：

1. 固定 N2 motion 文件目录，不把 N2 motion 放到 E1 数据目录。
2. 写清 motion 中 `JointNames` 必须与 N2 标准 joint order 匹配。
3. 写清 `KeyPosNames` 必须是 N2 link/body 名，而不是 E1 body 名。
4. 准备 motion schema checker。建议新增：

```text
TRAIN_E1Lab/scripts/motion/check_n2_mimic_motion.py
TRAIN_E1Lab/scripts/motion/check_n2_amp_motion.py
```

5. motion 未到位前，允许 task import/list 通过，但 reset/step/train/play 失败属于预期。

完成标准：

1. motion 数据到位后，可以先用 checker 验证格式和 joint/body 名，再启动训练。
2. motion 文件名可以自由命名，但配置中的 glob 路径必须能找到；真正关键的是文件内部 key、维度、joint order、body order。

## 8. M05: `Mimic-N2-18DOF` 迁移

目标：按 E1 Mimic 训练链路 1:1 迁移 N2 18DOF Mimic。

主要文件：

```text
TRAIN_E1Lab/source/NoetixN2/NoetixN2/tasks/mimic/__init__.py
TRAIN_E1Lab/source/NoetixN2/NoetixN2/tasks/mimic/config/n2/__init__.py
TRAIN_E1Lab/source/NoetixN2/NoetixN2/tasks/mimic/config/n2/flat_env_cfg_18dof.py
TRAIN_E1Lab/source/NoetixN2/NoetixN2/tasks/mimic/config/n2/agents/rsl_rl_him_ppo_18dof_cfg.py
TRAIN_E1Lab/source/NoetixN2/NoetixN2/tasks/mimic/tracking_env_cfg.py
TRAIN_E1Lab/source/NoetixN2/NoetixN2/tasks/mimic/env/manager_based_rl_mimic_env_18dof.py
TRAIN_E1Lab/source/NoetixN2/NoetixN2/tasks/mimic/mdp/
```

要做：

1. 注册 task id：

```text
Mimic-N2-18DOF
```

2. runner 保持：

```text
HimOnPolicyRunner
HIMPPO
```

3. robot cfg 使用：

```text
N2_18DOF_CFG
N2_18DOF_ACTION_SCALE
N2_18DOF_JOINT_NAMES
```

4. `tracking_env_cfg.py` 中 action joint names 不应继续用 `[".*"]` 作为最终协议；应显式使用 `N2_18DOF_JOINT_NAMES`，避免 articulation 解析顺序不稳定。
5. 替换 E1 Mimic 中所有 E1 body/joint：
   - anchor body
   - ankle dof names
   - body_names
   - feet/contact body
   - default pose
6. Mimic motion 文件路径指向：

```text
source/NoetixN2/NoetixN2/assets/datasets/mimic/n2_18dof/*.npz
```

7. 保持 N2 Mimic 不依赖 `NoetixE1.tasks.mimic.*`。

完成标准：

1. `Mimic-N2-18DOF` 能被 registry 发现。
2. 没有 motion 时，失败点应该清晰指向 motion 缺失，而不是 import 错误、E1 body 名错误或 joint 维度错误。
3. motion 到位后，能完成 reset、step、短训、play。

## 9. M06: `WalkRun-N2-AMP-10DOF` 迁移

目标：按 E1 WalkRun AMP 链路迁移 N2 10DOF 慢速前后左右旋转任务，上半身锁定到 default pose。

主要文件：

```text
TRAIN_E1Lab/source/NoetixN2/NoetixN2/tasks/walkrun/n2/__init__.py
TRAIN_E1Lab/source/NoetixN2/NoetixN2/tasks/walkrun/n2/walkrun_amp_10dof_cfg.py
TRAIN_E1Lab/source/NoetixN2/NoetixN2/tasks/walkrun/n2/agents/rsl_rl_amp_ppo_10dof_cfg.py
TRAIN_E1Lab/source/NoetixN2/NoetixN2/tasks/walkrun/n2/env/manager_based_rl_amp_env_10dof.py
TRAIN_E1Lab/source/NoetixN2/NoetixN2/tasks/walkrun/n2/mdp/
TRAIN_E1Lab/source/NoetixN2/NoetixN2/tasks/walkrun/n2/mdp/symmetry/n2_10dof.py
```

要做：

1. 注册 task id：

```text
WalkRun-N2-AMP-10DOF
```

2. runner 保持：

```text
AmpHimOnPolicyRunner
AMPHIMPPO
```

3. action 使用：

```text
N2_10DOF_JOINT_NAMES
N2_10DOF_ACTION_SCALE
```

4. motion 路径使用：

```text
source/NoetixN2/NoetixN2/assets/datasets/walkrun/n2_10dof/*
```

5. observation 保持当前 WalkRun 协议，并明确一帧维度：

```text
velocity_commands: 3
base_ang_vel: 3
euler_angle: 2
joint_pos: N
joint_vel: N
actions: N

one_frame = 8 + 3N
N2 10DOF one_frame = 38
history_stack=5 时 input = 190
```

6. reward、termination、event、curriculum 从 E1 迁移后要检查是否仍适合 N2：
   - foot body name
   - base body name
   - joint name regex
   - command range
   - yaw tracking
   - energy/smoothness penalty
   - AMP reward 与 task reward 权重
7. symmetry 使用 `n2_10dof.py`，不能复用 E1 symmetry。

完成标准：

1. task 能 import/list。
2. motion 到位后，能够 reset/step/train/play。
3. 训练日志、reward 项、AMP discriminator 输入维度与 10DOF motion 一致。

## 10. M07: `WalkRun-N2-AMP-18DOF` 迁移

目标：按 E1 WalkRun AMP 链路迁移 N2 18DOF 走跑任务，作为后续高速走跑和 RGMT encoder 替换实验的基础。

主要文件：

```text
TRAIN_E1Lab/source/NoetixN2/NoetixN2/tasks/walkrun/n2/walkrun_amp_18dof_cfg.py
TRAIN_E1Lab/source/NoetixN2/NoetixN2/tasks/walkrun/n2/agents/rsl_rl_amp_ppo_18dof_cfg.py
TRAIN_E1Lab/source/NoetixN2/NoetixN2/tasks/walkrun/n2/env/manager_based_rl_amp_env_18dof.py
TRAIN_E1Lab/source/NoetixN2/NoetixN2/tasks/walkrun/n2/mdp/symmetry/n2_18dof.py
```

要做：

1. 注册 task id：

```text
WalkRun-N2-AMP-18DOF
```

2. action 使用：

```text
N2_18DOF_JOINT_NAMES
N2_18DOF_ACTION_SCALE
```

3. motion 路径使用：

```text
source/NoetixN2/NoetixN2/assets/datasets/walkrun/n2_18dof/*
```

4. observation 一帧维度：

```text
one_frame = 8 + 3N
N2 18DOF one_frame = 62
history_stack=5 时 input = 310
```

5. 保持 `AmpHimOnPolicyRunner` / `AMPHIMPPO`，暂不在此迁移块替换 HIM estimator。
6. 如果后续做 RGMT encoder，另开独立迁移块，不和基础 N2 18DOF task 注册混在一起。

完成标准：

1. task 能 import/list。
2. 18DOF action/obs/reward/motion/discriminator 维度一致。
3. 没有 `WalkRun-N2-Flat-18DOF` 这种偏离 1:1 迁移逻辑的 task。

## 11. M08: AMP motion loader 中性化

目标：让 AMP JSON motion loader 真正变成 E1/N2 通用组件，而不是名字上改了但内部仍有 E1 歧义。

主要文件：

```text
TRAIN_E1Lab/rsl_rl/rsl_rl/utils/motion_loader.py
TRAIN_E1Lab/source/NoetixN2/NoetixN2/tasks/walkrun/n2/env/manager_based_rl_amp_env_10dof.py
TRAIN_E1Lab/source/NoetixN2/NoetixN2/tasks/walkrun/n2/env/manager_based_rl_amp_env_18dof.py
TRAIN_E1Lab/source/NoetixN2/NoetixN2/tasks/walkrun/n2/walkrun_amp_10dof_cfg.py
TRAIN_E1Lab/source/NoetixN2/NoetixN2/tasks/walkrun/n2/walkrun_amp_18dof_cfg.py
```

要做：

1. 使用中性类名：

```text
AmpJsonMotionLoader
```

2. 如果当前代码仍通过 `AmpJsonMotionLoader = MotionLoaderE1` alias 兼容，后续应继续收敛：
   - 错误信息从 `MotionLoaderE1` 改成 `AmpJsonMotionLoader`。
   - 文档和配置只写 `AmpJsonMotionLoader`。
   - E1 旧配置可临时继续用 `MotionLoaderE1`，但 N2 配置不要再写 E1 名称。
3. 检查 class-level layout 状态。如果同一个 Python 进程可能同时加载 E1 和 N2 motion，建议把 joint dim、key pos dim、frame indices 改成 instance-level 状态，避免 E1/N2 layout 互相污染。
4. motion loader 必须根据 motion 文件内部的 `JointNames` 和 `KeyPosNames` 动态确定维度。

完成标准：

1. N2 WalkRun 配置中 `motion_loader_name = "AmpJsonMotionLoader"`。
2. loader 能清楚报错：motion joint 数量、frame 宽度、key pos 数量、contact mask 是否匹配。
3. E1 和 N2 不会因为同进程加载不同 layout 造成隐式冲突。

## 12. M09: TRAIN play / ONNX export 迁移

目标：N2 checkpoint 训练完成后，可以通过 `play.py` 导出部署可用 ONNX，并写入正确 metadata。

主要文件：

```text
TRAIN_E1Lab/scripts/rsl_rl/play.py
TRAIN_E1Lab/rsl_rl/rsl_rl/utils/exporter.py
TRAIN_E1Lab/source/NoetixN2/NoetixN2/assets/robots/n2/n2.py
```

要做：

1. `play.py` import N2 task：

```python
import NoetixN2.tasks  # noqa: F401
```

2. `play.py` import N2 joint names：

```python
from NoetixN2.assets.robots.n2 import N2_10DOF_JOINT_NAMES, N2_18DOF_JOINT_NAMES
```

3. 在 `_DEPLOYMENT_JOINT_NAMES_BY_TASK` 中加入：

```python
"WalkRun-N2-AMP-10DOF": N2_10DOF_JOINT_NAMES
"WalkRun-N2-AMP-18DOF": N2_18DOF_JOINT_NAMES
```

4. 如果 Mimic/Dance ONNX 也要导出部署，必须先确认 Mimic/Dance observation layout 是否需要 wrapper。不能直接假设 WalkRun wrapper 可用于 Mimic。
5. `exporter.py` 保持通用，不为 N2 重写 exporter。重点检查 metadata 是否来自当前 env action manager 和 robot cfg。
6. 导出后用 metadata 检查工具验证：

```text
joint_names
default_joint_pos
action_scale
joint_stiffness
joint_damping
input shape
output shape
```

完成标准：

1. `WalkRun-N2-AMP-10DOF` ONNX 输出 action 顺序等于 `N2_10DOF_JOINT_NAMES`。
2. `WalkRun-N2-AMP-18DOF` ONNX 输出 action 顺序等于 `N2_18DOF_JOINT_NAMES`。
3. ONNX metadata 可被 CTRL 侧严格检查通过。

## 13. M10: TRAIN sim2sim 入口迁移

目标：导出的 N2 ONNX 能先在 sim2sim 中验证，再进入 CTRL Gazebo。

主要新增文件：

```text
TRAIN_E1Lab/scripts/sim2sim/sim2sim_walkrun_n2_10dof.py
TRAIN_E1Lab/scripts/sim2sim/sim2sim_walkrun_n2_18dof.py
TRAIN_E1Lab/scripts/sim2sim/sim2sim_mimic_n2_18dof.py
```

要做：

1. 复制 E1 sim2sim 公共逻辑，但入口文件和默认配置使用 N2。
2. MJCF 使用：

```text
source/NoetixN2/NoetixN2/assets/robots/n2/mjcf/n2_10dof.xml
source/NoetixN2/NoetixN2/assets/robots/n2/mjcf/n2_18dof.xml
```

3. joint order 使用 `N2_*DOF_JOINT_NAMES`。
4. action scale/default pose 从 ONNX metadata 或 N2 cfg 读取，不能手写另一套。
5. Mimic sim2sim 如果 observation layout 与 WalkRun 不同，需要单独实现输入构造。

完成标准：

1. N2 10DOF walkrun ONNX 能在 sim2sim 中加载并输出正确维度 action。
2. N2 18DOF walkrun ONNX 能在 sim2sim 中加载并输出正确维度 action。
3. sim2sim 中显示的 joint order 与 ONNX metadata 完全一致。

## 14. M11: CTRL N2 description / Gazebo 资产

目标：CTRL Gazebo 能独立加载 N2，而不是借用 E1 description。

主要新增路径：

```text
CTRL_E1Base/src/legged_rl/legged_robot/n2/legged_n2_description/
CTRL_E1Base/src/legged_rl/legged_robot/n2/legged_n2_description/urdf/n2_10dof.urdf
CTRL_E1Base/src/legged_rl/legged_robot/n2/legged_n2_description/urdf/n2_18dof.urdf
CTRL_E1Base/src/legged_rl/legged_robot/n2/legged_n2_description/meshes/
```

主要修改/新增：

```text
CTRL_E1Base/src/legged_rl/legged_base/legged_gazebo/launch/n2_empty_world.launch
CTRL_E1Base/src/legged_rl/legged_base/legged_gazebo/config/n2_default.yaml
```

要做：

1. 从 TRAIN N2 URDF/meshes 迁移到 CTRL N2 description。
2. 为 Gazebo 补齐必要 transmission、ros_control、gazebo plugin、collision/contact、IMU frame。
3. `n2_empty_world.launch` 从 `legged_n2_description` 读取 URDF，并写入 ROS 参数：

```text
legged_robot_description
```

4. `spawn_model` 使用：

```text
-param legged_robot_description -urdf -model n2
```

5. `n2_default.yaml` 配置 N2 IMU 和 contact：

```text
contacts: ["L_leg_ankle_link", "R_leg_ankle_link"]
```

实际 contact 名以 Gazebo plugin 可读取的 link/joint 名为准。

完成标准：

1. Gazebo 中能 spawn N2 10DOF / 18DOF。
2. `controller_manager` 能看到 N2 joints。
3. IMU 和 contacts topic 正常发布。

## 15. M12: CTRL N2 controller yaml

目标：让 CTRL 控制器配置与 N2 ONNX metadata 对齐。

主要新增文件：

```text
CTRL_E1Base/src/legged_rl/rl_controller/rl_controllers/config/n2_10dof_ac.yaml
CTRL_E1Base/src/legged_rl/rl_controller/rl_controllers/config/n2_18dof_ac.yaml
CTRL_E1Base/src/legged_rl/rl_controller/rl_controllers/config/n2_kd.yaml
CTRL_E1Base/src/legged_rl/rl_controller/rl_controllers/policy/n2/
CTRL_E1Base/src/legged_rl/rl_controller/rl_controllers/motion_files/n2/
```

要做：

1. `policy_joint_names` 完全等于 TRAIN `N2_*DOF_JOINT_NAMES`。
2. `control_joint_names` 使用 Gazebo/ros_control 暴露的 N2 joint names。若与 policy order 不同，必须在 controller 内显式建立 `policy_joint -> control_joint` mapping。
3. 10DOF walkrun 维度：

```text
actions_size = 10
one_frame_observation_size = 38
stack_size = 5
onnx_input_size = 190
```

4. 18DOF walkrun 维度：

```text
actions_size = 18
one_frame_observation_size = 62
stack_size = 5
onnx_input_size = 310
```

5. `policy_file` 指向 N2 ONNX。
6. `enable_dance`、`dance_policy_file`、`motion_file` 的最终处理方式要分开：
   - 如果当前只验证 WalkRun，可配置关闭 dance。
   - 最终完整迁移必须补齐 N2 Mimic/Dance policy 和 motion，不应长期依赖 E1 dance 配置。

完成标准：

1. CTRL 启动时 ONNX metadata joint_names 与 yaml `policy_joint_names` 完全一致。
2. ONNX input/output shape 与 yaml 维度一致。
3. 不再出现 E1 joint alias normalization 参与 N2 检查。

## 16. M13: CTRL controller 代码解耦

目标：控制器逻辑支持 N2，同时不破坏 E1。

主要文件：

```text
CTRL_E1Base/src/legged_rl/rl_controller/rl_controllers/src/RLControllerBase.cpp
CTRL_E1Base/src/legged_rl/rl_controller/rl_controllers/include/rl_controllers/RLControllerBase.h
CTRL_E1Base/src/legged_rl/rl_controller/rl_controllers/src/AcController.cpp
CTRL_E1Base/src/legged_rl/rl_controller/rl_controllers/include/rl_controllers/AcController.h
```

推荐结构：

```text
方案 A: 新增 n2_rl_controllers 包
  优点: E1/N2 解耦最清楚
  缺点: 会复制一部分 ONNX/obs/action 公共逻辑

方案 B: 保留 rl_controllers 包，但抽 RobotProfile
  优点: 公共逻辑复用更好
  缺点: 如果抽象不彻底，容易形成 robot_type 分支堆积
```

本次要求强调完全解耦，因此更推荐：

```text
新增 N2 controller 或 N2 RobotProfile，不在 E1 hardcode 上打补丁。
```

要做：

1. 把当前 E1-only 结构替换或隔离：
   - `RLControllerBase::JointState`
   - `standjointState_`
   - `liejointState_`
   - `stateToMap`
   - `isLowDampingStandJoint`
   - `NormalizePolicyJointName`
   - `computeObservationDance` 中 E1 腰部姿态转换
2. N2 stand/lie/default pose 从 yaml 或 robot profile 读取，不写死在 E1 struct。
3. WalkRun observation 构造必须与 TRAIN N2 observation 对齐：

```text
velocity_commands
base_ang_vel
euler_angle
joint_pos - default_joint_pos
joint_vel
last_action
history_stack
```

4. action 执行必须与 TRAIN action 公式一致：

```text
pos_des = action * action_scale + default_joint_pos
```

5. ONNX metadata strict check 保留：
   - joint names
   - action scale
   - default joint pos
   - stiffness
   - damping
   - input/output shape

完成标准：

1. E1 controller 仍可按 E1 配置启动。
2. N2 controller 不依赖 E1 简写 joint 名、E1 腰关节、E1 ankle 结构。
3. N2 controller 失败时错误信息指向明确接口，例如 metadata mismatch、obs shape mismatch、joint handle missing。

## 17. M14: CTRL N2 Gazebo 启动链路

目标：提供 N2 Gazebo 一键启动脚本。

主要新增文件：

```text
CTRL_E1Base/simulation_n2_10dof.sh
CTRL_E1Base/simulation_n2_18dof.sh
CTRL_E1Base/src/legged_rl/rl_controller/rl_controllers/launch/ac_start_n2.launch
CTRL_E1Base/src/legged_rl/rl_controller/rl_controllers/launch/load_n2_ac_controller.launch
```

要做：

1. 顶层脚本设置：

```bash
ROBOT_TYPE=n2
ROBOT_MODEL=n2_10dof 或 n2_18dof
POLICY_FILE=.../rl_controllers/policy/n2/...
```

2. launch 链路：

```text
simulation_n2_*.sh
  -> ac_start_n2.launch
  -> n2_empty_world.launch
  -> load_n2_ac_controller.launch
  -> controllers/n2_ac_controller 或 controllers/ac_controller 的 N2 profile
```

3. 不让 N2 通过 `e1_empty_world.launch` 或 `legged_e1_description` 启动。

完成标准：

1. Gazebo 能启动 N2 世界。
2. N2 controller 能加载。
3. policy 文件缺失时只报 policy 缺失，不报 E1 URDF、E1 joint、E1 dance shape。

## 18. M15: CTRL N2 Mimic / Dance 链路

目标：完整迁移时，N2 不只支持 walk，还要支持 Mimic/Dance 相关 policy 和 motion。

主要文件：

```text
CTRL_E1Base/src/legged_rl/rl_controller/rl_controllers/config/n2_18dof_ac.yaml
CTRL_E1Base/src/legged_rl/rl_controller/rl_controllers/policy/n2/
CTRL_E1Base/src/legged_rl/rl_controller/rl_controllers/motion_files/n2/
CTRL_E1Base/src/legged_rl/rl_controller/rl_controllers/src/AcController.cpp
```

要做：

1. 区分 WalkRun policy 和 Mimic/Dance policy：
   - 不同 ONNX input shape
   - 不同 observation layout
   - 不同 motion/reference 输入
2. 如果 N2 Dance 使用 Mimic policy，需要为 N2 实现对应 observation 构造，不能复用 E1 `computeObservationDance()` 中的腰关节假设。
3. N2 dance/mimic motion 文件放到：

```text
rl_controllers/motion_files/n2/
```

4. 如果暂时只验证 WalkRun，允许配置 `enable_dance=false`；但最终完整迁移必须补齐 N2 dance/mimic 链路。

完成标准：

1. N2 walk-only 启动不会被 dance policy shape 阻塞。
2. N2 dance/mimic policy 到位后，可以独立加载、检查 metadata、构造 observation、输出 action。
3. E1 dance motion 和 N2 dance motion 不混用。

## 19. M16: CTRL N2 真机硬件接口

目标：完成 N2 真机部署硬件层。这个迁移块依赖外部硬件信息，不应凭 E1 代码猜。

主要新增路径：

```text
CTRL_E1Base/src/legged_rl/legged_robot/n2_hw/legged_n2_hw/
CTRL_E1Base/src/legged_rl/legged_robot/n2_hw/legged_n2_hw/config/
CTRL_E1Base/src/legged_rl/legged_robot/n2_hw/legged_n2_hw/launch/
CTRL_E1Base/src/legged_rl/legged_robot/n2_hw/legged_n2_hw/src/
CTRL_E1Base/src/legged_rl/legged_robot/n2_hw/legged_n2_hw/include/
```

必须向硬件/领导确认的信息：

1. N2 真机通信方式：
   - EtherCAT
   - CAN
   - UDP / SDK
   - 其他
2. 网卡名称、IP、实时线程要求。
3. motor/slave/node 拓扑：

```text
motor_id / slave_id / node_id -> joint_name
```

4. 每个电机方向、零点、编码器单位、减速比。
5. 每个关节限位、速度限位、力矩限位。
6. IMU frame、安装方向、坐标系约定。
7. 急停、上电、使能、站立、趴下、安全限幅策略。
8. 真机可控 DOF 是 10DOF 还是 18DOF，手臂是否参与控制。

要做：

1. 不复用 `legged_e1_hw` 作为 N2 硬件包。
2. 新增 `legged_n2_hw`，内部把硬件 motor order 映射到软件 joint names。
3. 对 controller 暴露的 joint handle 名必须仍是 N2 标准 joint names。

完成标准：

1. `legged_n2_hw` 能 read/write N2 状态和命令。
2. controller 侧不需要知道 motor/slave 顺序，只处理 joint name。
3. 硬件异常不会绕过安全限制。

## 20. M17: 分层验证与交付清单

目标：每完成一层迁移，都有明确的验收动作。

### 20.1 TRAIN 静态验证

要验证：

```text
NoetixN2 可 import
N2 task 可注册
N2 cfg 不引用 NoetixE1
N2 joint names/action scale/default pose 维度一致
N2 motion 路径存在或缺失错误清晰
```

建议检查：

```bash
python scripts/list_envs.py
python -c "import NoetixN2.tasks"
```

### 20.2 TRAIN motion 到位后验证

Mimic：

```bash
python scripts/rsl_rl/train.py --task=Mimic-N2-18DOF --headless --num_envs=64 --max_iterations=1
```

WalkRun 10DOF：

```bash
python scripts/rsl_rl/train.py --task=WalkRun-N2-AMP-10DOF --headless --num_envs=64 --max_iterations=1
```

WalkRun 18DOF：

```bash
python scripts/rsl_rl/train.py --task=WalkRun-N2-AMP-18DOF --headless --num_envs=64 --max_iterations=1
```

完成标准：

1. env 能 reset。
2. env 能 step。
3. reward、observation、action、AMP discriminator 不出现维度错误。
4. checkpoint 能保存到 `logs/rsl_rl/...`。

### 20.3 TRAIN play / ONNX export 验证

要验证：

```text
play 能加载 N2 checkpoint
ONNX 能导出
ONNX metadata 正确
ONNX input/output shape 正确
joint_names 顺序正确
```

完成标准：

1. N2 10DOF ONNX metadata 中 `joint_names` 长度为 10。
2. N2 18DOF ONNX metadata 中 `joint_names` 长度为 18。
3. metadata 顺序与 `N2_*DOF_JOINT_NAMES` 完全一致。

### 20.4 sim2sim 验证

要验证：

```text
MJCF 能加载
ONNX 能加载
policy 输出维度正确
action scale/default pose 正确
机器人不因 joint order 错误立即异常
```

完成标准：

1. 静止 command 下机器人姿态合理。
2. 小速度 command 下动作方向合理。
3. 左右转 command 下 yaw 方向正确。

### 20.5 CTRL Gazebo 验证

要验证：

```text
N2 URDF spawn
controller load
ONNX metadata check
observation shape
action shape
joint command publish
Gazebo 站立和小速度运动
```

完成标准：

1. `spawn_model` 成功。
2. `controller_manager` 成功加载 N2 controller。
3. metadata mismatch、shape mismatch 不再出现。
4. command 为 0 时能站立或进入默认姿态。
5. 小速度 command 下能按预期移动。

### 20.6 真机验证

前置条件：

```text
N2 硬件拓扑确认
legged_n2_hw 完成
安全策略完成
Gazebo 验证通过
低增益站立验证通过
```

完成标准：

1. 空载/架空 read/write 正常。
2. 低增益站立安全。
3. 小幅 command 响应方向正确。
4. 急停和限位有效。

## 21. 最终迁移顺序建议

严格建议按下面顺序执行：

1. M00：整理分支和基线。
2. M01：固定 N2 接口协议，确认 `N2_*DOF_JOINT_NAMES` 是唯一软件标准顺序。
3. M02：补齐 `NoetixN2` 包级解耦，确保 train/play/list 能发现 N2 task。
4. M03：确认 N2 robot asset、body name、contact name、base name。
5. M04：建立 N2 motion 数据目录和格式检查工具。
6. M05：完成 `Mimic-N2-18DOF` 代码链路。
7. M06：完成 `WalkRun-N2-AMP-10DOF` 代码链路。
8. M07：完成 `WalkRun-N2-AMP-18DOF` 代码链路。
9. M08：收敛 `AmpJsonMotionLoader`，降低 E1/N2 混用风险。
10. M09：补齐 `play.py` 的 N2 ONNX 导出和 deployment joint order 映射。
11. M10：新增 N2 sim2sim 入口。
12. motion 到位后：训练 N2 Mimic / WalkRun，并导出 ONNX。
13. M11：CTRL 侧新增 N2 description 和 Gazebo 资产。
14. M12：CTRL 侧新增 N2 controller yaml、policy 目录、motion 目录。
15. M13：CTRL controller 解耦，去掉 N2 路径上的 E1 hardcode。
16. M14：新增 N2 Gazebo 启动脚本和 launch。
17. M15：补齐 N2 Mimic/Dance 部署链路。
18. M16：硬件信息齐全后，再做 N2 真机硬件接口。
19. M17：按静态、短训、play、ONNX、sim2sim、Gazebo、真机逐层验收。

## 22. 当前仍然阻塞完整闭环的信息

这些不是代码迁移不能写的理由，但会阻塞最终运行验证：

1. N2 Mimic `.npz` motion 文件未提供。
2. N2 AMP JSON motion 文件未提供。
3. N2 policy checkpoint 未训练完成。
4. N2 ONNX 尚未导出。
5. CTRL 侧 N2 Gazebo URDF 是否需要额外 transmission/gazebo tag 尚未最终验证。
6. N2 真机硬件拓扑、通信方式、电机映射、IMU 坐标系、限位和安全策略未确认。

其中 1 到 4 阻塞 TRAIN 完整训练和 Gazebo policy 验证；5 阻塞 CTRL Gazebo；6 只阻塞真机，不阻塞 TRAIN 代码迁移和 Gazebo 代码迁移。

## 23. 每个阶段的核心交付物

TRAIN 侧最终交付物：

```text
source/NoetixN2/NoetixN2/assets/robots/n2/
source/NoetixN2/NoetixN2/assets/datasets/mimic/n2_18dof/
source/NoetixN2/NoetixN2/assets/datasets/walkrun/n2_10dof/
source/NoetixN2/NoetixN2/assets/datasets/walkrun/n2_18dof/
source/NoetixN2/NoetixN2/tasks/mimic/
source/NoetixN2/NoetixN2/tasks/walkrun/n2/
scripts/rsl_rl/play.py N2 export mapping
scripts/sim2sim/*n2*
logs/rsl_rl/.../N2 checkpoints
exported N2 ONNX files with metadata
```

CTRL 侧最终交付物：

```text
legged_n2_description
n2_empty_world.launch
n2_default.yaml
n2_10dof_ac.yaml
n2_18dof_ac.yaml
policy/n2/*.onnx
motion_files/n2/*
simulation_n2_10dof.sh
simulation_n2_18dof.sh
N2 controller 或 N2 RobotProfile
legged_n2_hw  # 真机阶段
```

最终判断标准：

```text
TRAIN 能训练 N2 Mimic / N2 AMP
TRAIN 能导出 N2 ONNX
sim2sim 能加载 N2 ONNX
CTRL Gazebo 能加载 N2 robot 和 N2 policy
CTRL metadata 检查通过
N2 在 Gazebo 中能按 command 行走/转向/执行对应 mimic 或 dance
真机阶段只在硬件信息齐全、安全策略完成后推进
```

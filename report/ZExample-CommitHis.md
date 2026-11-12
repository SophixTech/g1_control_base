# 提交历史记录

## 2026-07-22 11:23:21 +0800 - fa8a5d052d50fd83055cb20e4d55300e61317f7f

标题：重构 E2 WalkRun motion 数据集

简要：
- `e2_23dof` 改为未修复对照集合，并加入两条 time-reverse synthetic backward motion。
- 新增 `e2_23dof_corrected` 修复后集合，包含 11 条 motion、M06 manifest 和 selection manifest。
- 删除旧 `e2_23dof_2` 对照目录，去掉未确认的 `067` 快跑副本。
- 更新数据集 README，记录 corrected/uncorrected、backward synthetic 和类别权重说明。

验证：
- Python JSON 解析检查 `e2_23dof` 与 `e2_23dof_corrected` 共 22 条 motion TXT。
- `git diff --check` 与 `git diff --cached --check`。

追溯：`git show fa8a5d052d50fd83055cb20e4d55300e61317f7f`

## 2026-07-22 11:22:52 +0800 - b99f79c0111ee73a29f84614dc5ffb3233b6cc54

标题：微调 E2 WalkRun 质量随机化和足力阈值

简要：
- E2 WalkRun startup 质量扰动 body 从 `waist_yaw_link` 调整为 `waist_pitch_link`。
- `feet_force` 阈值从 400/600 调整为 390/580。

验证：
- `python3 -m py_compile` 检查 E2 WalkRun 配置。
- `git diff --cached --check`。

追溯：`git show b99f79c0111ee73a29f84614dc5ffb3233b6cc54`

## 2026-07-22 11:22:32 +0800 - fcbf1b7d994f08b18bf65efa9611ae0fb47fd74b

标题：更新 E2 URDF 惯性参数

简要：
- 更新 E2 23DOF URDF 多个 link 的 inertial origin、mass 和 inertia 数值。
- 同步规范部分科学计数法/小数格式，保持 XML 可解析。

验证：
- Python `xml.etree.ElementTree` 解析 URDF。
- `git diff --cached --check`。

追溯：`git show fcbf1b7d994f08b18bf65efa9611ae0fb47fd74b`

## 2026-07-22 11:22:08 +0800 - 91ac10af0e25ec2bf9cef8ba4a577e24da958ee8

标题：新增 E2 AMP 时间反演工具

简要：
- 新增 `scripts/motion/reverse_e2_amp.py`，可将 E2 forward AMP motion 按时间倒序生成 synthetic backward motion。
- 输出时重置 root 水平原点、重算 root/joint velocity，并写入 synthetic provenance metadata。

验证：
- `python3 -m py_compile` 检查新增脚本。
- `git diff --cached --check`。

追溯：`git show 91ac10af0e25ec2bf9cef8ba4a577e24da958ee8`

## 2026-07-21 20:06:15 +0800 - b6b9f15c8e13649507c2f3cbc42806d214712b77

标题：加入 E2 WalkRun 23DOF motion 数据集

简要：
- `e2_23dof` 加入当前 E2 WalkRun 默认训练 motion、M06 审计 manifest 和选择 manifest。
- 新增 `e2_23dof_2` 未修复对照数据集，用于和 corrected/final motion 做可视化对比。
- 更新 E2 数据集 README，记录类别、权重和当前缺失/保留状态。

验证：
- Python JSON 解析检查 19 条 motion TXT。
- `git diff --cached --check`。

追溯：`git show b6b9f15c8e13649507c2f3cbc42806d214712b77`

## 2026-07-21 20:05:27 +0800 - 22f8c7f2f89deda95be9cbb560105662d7771d15

标题：完善 E2 motion 转换修复工具链

简要：
- 新增 E2 motion 通用加载/审计、PKL 转 AMP、AMP 检查、分类整理、脚底修复和 URDF FK 工具。
- `play_animation.py` 支持 `--motion-dir` 递归播放 AMP TXT。
- `scripts/rsl_rl/play.py` 增加 E2 23DOF ONNX 导出 joint order metadata。
- E2 contract 调整默认 root height，并导出 root height/初始脚底 clearance。
- 删除旧的 `scripts/robot/check_e2_contract.py`，相关检查能力迁移到 motion 工具链。

验证：
- `python3 -m py_compile` 检查相关 motion/播放脚本。
- `git diff --check` 与 `git diff --cached --check`。

追溯：`git show 22f8c7f2f89deda95be9cbb560105662d7771d15`

## 2026-07-21 20:05:00 +0800 - ee1341b7f944be0d0df0a361d8608c6d3f66dd85

标题：忽略 E2 分类 motion 中间目录

简要：
- `.gitignore` 增加 `e2_23dof_categorized/` 和 `e2_23dof_corrected_categorized/`，避免提交分类/修复中间产物。

验证：
- `git diff --cached --check`。

追溯：`git show ee1341b7f944be0d0df0a361d8608c6d3f66dd85`

## 2026-07-21 13:49:20 +0800 - d25814513c358dd8ed88215a4d85a8601c7d0f6b

标题：接入 NoetixE2 到训练工具链

简要：
- README 增加 `WalkRun-E2-AMP-23DOF` 环境入口和 NoetixE2 安装说明。
- 精确环境文档和 `install-exact.sh` 增加 NoetixE2 editable 安装与版本输出。
- `pyrightconfig.json` 增加 `source/NoetixE2`。
- 训练、回放、motion 播放和环境列表脚本导入 NoetixE2 tasks，并让 `list_envs.py` 显示 E2 环境。

验证：
- `python3 -m py_compile` 检查相关脚本。
- `git diff --check` 与 `git diff --cached --check`。

追溯：`git show d25814513c358dd8ed88215a4d85a8601c7d0f6b`

## 2026-07-21 13:48:48 +0800 - fc62459d129ecf2e9364e45f4ef04f5ec37239a7

标题：新增 NoetixE2 WalkRun 23DOF 扩展

简要：
- 新增独立 `source/NoetixE2` 扩展，包含包配置、actuator、manager、terrain 等基础模块。
- 新增 E2 23DOF 机器人 contract、URDF、mesh 资产和 Isaac Lab articulation 配置。
- 新增 `WalkRun-E2-AMP-23DOF` 任务注册、环境、command/reward/event/observation/curriculum、对称性和 RSL-RL AMP PPO 配置。
- 新增 `scripts/robot/check_e2_contract.py`，用于离线检查 E2 URDF、mesh、joint contract 和对称性约束。
- 规范化 E2 URDF 行尾格式，避免 trailing whitespace。

验证：
- `python3 -m py_compile` 检查 E2 扩展关键 Python 文件。
- `git diff --check` 与 `git diff --cached --check`。

追溯：`git show fc62459d129ecf2e9364e45f4ef04f5ec37239a7`

## 2026-07-21 11:31:21 +0800 - 616a92ae4e1d9463f041b6f5c9a07097ee2b362b

标题：使用 N2 脚底采样点计算步态高度

简要：
- N2 18DOF 机器人资产新增左右脚踝底面采样点 `N2_18DOF_FOOT_SOLE_POINTS`，并从 `assets.robots.n2` 导出。
- 新增 `foot_sole_height_w`，将脚底采样点转换到世界坐标系后取最低点高度。
- `AlternatingStepAirTimeReward` 改为基于脚底最低点计算摆动脚离地高度，避免直接使用 ankle link 原点高度。
- N2 18DOF WalkRun 配置接入脚底采样点，并将交替步态高度奖励 scale 调整为 1.0。

验证：
- `python3 -m py_compile` 检查本次修改相关 Python 文件。
- `git diff --check` 与 `git diff --cached --check`。

追溯：`git show 616a92ae4e1d9463f041b6f5c9a07097ee2b362b`


## 2026-07-20 10:09:37 +0800 - b46b6f9009a9a705c6e8c54f3d855dd9d16ae687

标题：调整 N2 WalkRun 交替步态奖励

简要：
- 新增 `AlternatingStepAirTimeReward`，结合摆动脚离地高度、步态相位、左右脚交替落地和单脚支撑超时计算奖励。
- N2 18DOF 配置用交替步态奖励替换原 `feet_air_time`，并要求左右踝按顺序绑定 contact/body。
- 移除左右踝/膝 lateral separation 奖励，恢复 `feet_too_near` 约束。
- 调整 contact force 阈值、yaw tracking std、feet slide/action rate 权重，并将 episode length 改为 20 秒。
- 暂停 `lin_x_undershoot` 和 `energy` 奖励项。

验证：
- `python3 -m py_compile` 检查本次修改相关 Python 文件。
- `git diff --check` 与 `git diff --cached --check`。

追溯：`git show b46b6f9009a9a705c6e8c54f3d855dd9d16ae687`

## 2026-07-17 11:50:36 +0800 - 4a37af20b2af62c4d83f19fc2d498bee5754febd

标题：增加 N2 WalkRun 支撑稳定性奖励

简要：
- 新增 `prolonged_double_support`，惩罚移动命令下持续双脚支撑。
- 新增 `support_foot_orientation`，惩罚支撑脚受力方向与脚底姿态偏差过大。
- N2 18DOF 配置接入上述奖励，并降低 feet contact 权重、提高 feet slide 惩罚。
- 左右踝/膝横向间距阈值提高，强化步态交叉约束。

验证：
- `python3 -m py_compile` 检查本次修改相关 Python 文件。
- `git diff --check` 与 `git diff --cached --check`。

追溯：`git show 4a37af20b2af62c4d83f19fc2d498bee5754febd`

## 2026-07-17 11:49:57 +0800 - b9c1950d9b0e8e9f4959c09a4956ebcf1e186702

标题：合并 N2 前进 AMP 条件为 forward_motion

简要：
- AMP condition 从 `forward`/`forward_yaw` 合并为 `forward_motion`，纯前进和前进转向共用同一专家条件。
- N2 command 分类同步使用 `forward_motion`，condition 列表简化为 stand、forward_motion、backward、pure_yaw。
- motion 转换脚本和数据集同步写入 `AmpCondition=forward_motion`。
- 删除 `n2_run_medium_003.txt`，当前 N2 18DOF WalkRun motion 数量为 19 条。
- 当前 motion 权重总和为 0.9904255319，按现有文件原样提交，后续如需可再归一化。

验证：
- `python3 -m py_compile` 检查本次修改相关 Python 文件。
- Python JSON 解析 19 条 motion，统计当前 condition 权重。
- `git diff --check` 与 `git diff --cached --check`。

追溯：`git show b9c1950d9b0e8e9f4959c09a4956ebcf1e186702`

## 2026-07-17 11:49:24 +0800 - aa24f64f8c3db3d4b201451f71d8f73bca9523fd

标题：调整精确环境安装为复用现有 venv

简要：
- `environment/install-exact.sh` 改为复用当前激活的 venv 或显式 `VENV_PATH`，不再默认创建 `.venv-repro`。
- 增加目标 venv、Python 3.11 和 pip 可用性检查；缺少 pip 时用 uv bootstrapping。
- README 更新为先创建固定路径 uv venv，再运行安装脚本的流程。
- 保留 IsaacLab 依赖、lock 安装和 editable package 安装逻辑。

验证：
- `bash -n environment/install-exact.sh`
- `git diff --check` 与 `git diff --cached --check`。

追溯：`git show aa24f64f8c3db3d4b201451f71d8f73bca9523fd`

## 2026-07-16 10:30:46 +0800 - fb1ab4594546245820720dd157d474f5f1b6d0ca

标题：调整 N2 WalkRun AMP 奖励配置

简要：
- N2 18DOF AMP 奖励系数从 0.6 调到 0.7，`amp_reward_lerp` 从 0.8 调到 0.7。
- 新增通用 `feet_air_time` 奖励，替换原转向单脚支撑奖励。
- 新增左右踝、左右膝横向间距惩罚，替换原 `feet_too_near`。
- AMP reference observation horizon 从 4 提高到 10。

验证：
- `python3 -m py_compile` 检查本次修改相关 Python 文件。
- `git diff --check` 与 `git diff --cached --check`。

追溯：`git show fb1ab4594546245820720dd157d474f5f1b6d0ca`

## 2026-07-16 10:30:19 +0800 - daa7e2f40ea534b651f51fc8bc485c6c6a0cb0a1

标题：按 AMP 条件均衡采样判别器数据

简要：
- ReplayBuffer 支持按 label values 均衡抽样，避免条件化 AMP 判别器 mini-batch 被高频 condition 主导。
- AMP discriminator 更新时，policy 样本按 condition 均衡采样，expert 样本按 policy condition 精确匹配。
- MotionLoader 预缓存每个 condition 的样本索引，并新增 `sample_by_condition_ids`。
- 新增单测覆盖 replay buffer 条件均衡采样和 motion loader 条件匹配采样。

验证：
- `python3 -m py_compile` 检查 RSL-RL 相关 Python 文件和新增测试。
- `git diff --check` 与 `git diff --cached --check`。
- `python3 -m pytest rsl_rl/tests/test_conditioned_amp.py` 未执行成功：当前环境未安装 `pytest`。

追溯：`git show daa7e2f40ea534b651f51fc8bc485c6c6a0cb0a1`

## 2026-07-16 10:28:16 +0800 - fbddc8ed1c9d7a646760e569d940de3eb25a9f27

标题：调整 N2 WalkRun AMP motion 权重

简要：
- 调整 `scripts/motion/n2_pkl_to_amp.py` 中 N2 WalkRun curated motion 权重。
- 权重按当前有 AMP condition 的命令比例归一：stand 0.18、forward 0.12、backward 0.17、pure_yaw 0.36、forward_yaw 0.17。
- 保留 forward 条件内部原有 walk/slow-run/fast-run 比例。
- 同步更新 20 条 N2 18DOF WalkRun AMP TXT 数据集中的 `MotionWeight`。

验证：
- `python3 -m py_compile scripts/motion/n2_pkl_to_amp.py`
- Python JSON 解析 20 条 motion，确认总权重为 1.0。
- `git diff --cached --check`

追溯：`git show fbddc8ed1c9d7a646760e569d940de3eb25a9f27`

## 2026-07-14 19:43:02 +0800 - cf3d10982f3453f028076648745550b4b1964857

标题：将转向前进 AMP 条件改为 forward_yaw

简要：
- AMP condition 名称从 `moving_yaw` 调整为 `forward_yaw`。
- 命令分类只将前进且带 yaw 的样本归入 `forward_yaw`，横向带 yaw 不再进入该 condition。
- 命令统计指标恢复为 `command_rate/forward_yaw`。
- motion 转换脚本和 4 条 turn_moving 数据集同步写入 `AmpCondition=forward_yaw`。

验证：
- `python3 -m py_compile` 检查本次修改相关 Python 文件。
- `git diff --check` 与 `git diff --cached --check`。

追溯：`git show cf3d10982f3453f028076648745550b4b1964857`

## 2026-07-14 19:42:33 +0800 - bfd76af03a3012a42bd9d28b1350c5dfc7ffc3e1

标题：移除 AMP 方向不变判别器掩码

简要：
- 移除 Discriminator 中按 condition 额外屏蔽水平速度维度的 direction-invariant mask 逻辑。
- Runner 不再读取 `amp_direction_invariant_conditions` 并传入判别器。
- N2 18DOF AMP 配置删除 `amp_direction_invariant_conditions`。
- 删除对应方向不变 mask 单测，保留条件化判别器与 replay buffer 基础测试。

验证：
- `python3 -m py_compile` 检查本次修改相关 Python 文件。
- `git diff --check` 与 `git diff --cached --check`。
- `python3 -m pytest rsl_rl/tests/test_conditioned_amp.py` 未执行成功：当前环境未安装 `pytest`。

追溯：`git show bfd76af03a3012a42bd9d28b1350c5dfc7ffc3e1`

## 2026-07-14 18:14:12 +0800 - 2c6a454bc40dece710d4a9eaaae35eaa1ceb4e18

标题：接入 N2 WalkRun 条件化 AMP

简要：
- N2 WalkRun 增加 AMP command condition 分类：stand、forward、backward、pure_yaw、moving_yaw。
- 环境 step 将 `amp_condition_ids` 传给 AMP reward/判别器训练。
- N2 18DOF AMP 配置接入 condition names，并对 moving_yaw 做方向不变速度维度屏蔽。
- 命令采样新增纯横向样本比例，指标从 `forward_yaw` 调整为 `moving_yaw`。
- motion 转换脚本写入 `MotionCategory` 和 `AmpCondition`，并修复反向轨迹 root XY 原点 alias 问题。
- 刷新 N2 18DOF WalkRun 数据集 metadata，合成后退 motion 同步更新轨迹数值。

验证：
- `python3 -m py_compile` 检查本次修改相关 Python 文件。
- `git diff --check` 与 `git diff --cached --check`。

追溯：`git show 2c6a454bc40dece710d4a9eaaae35eaa1ceb4e18`

## 2026-07-14 18:13:47 +0800 - 792a2bcdc9c98385e2310e0a13390ff70ace5f66

标题：支持条件化 AMP 判别器

简要：
- RSL-RL AMP 判别器支持按 condition head 输出，并支持部分 condition 的方向不变特征屏蔽。
- ReplayBuffer 支持保存 condition label，AMP policy/expert 样本和多卡 gather 同步携带 condition ids。
- AMP reward 对未支持命令使用无条件 ID 跳过 style reward，只保留任务奖励。
- MotionLoader 支持读取 `AmpCondition` 并返回条件标签。
- 新增 `test_conditioned_amp.py` 覆盖无条件兼容、未支持命令跳过、方向不变 mask 和 labeled replay buffer。

验证：
- `python3 -m py_compile` 检查 RSL-RL 相关 Python 文件和新增测试。
- `git diff --check` 与 `git diff --cached --check`。
- `python3 -m pytest rsl_rl/tests/test_conditioned_amp.py` 未执行成功：当前环境未安装 `pytest`。

追溯：`git show 792a2bcdc9c98385e2310e0a13390ff70ace5f66`

## 2026-07-14 09:54:29 +0800 - 3bd6c3cc7a2877738ad14d05492f18f8ff139b4e

标题：调整 WalkRun 课程与 AMP 权重

简要：
- E1 23DOF WalkRun 课程 `reward_gate_ratio` 从 0.75 降到 0.70。
- N2 18DOF AMP `amp_reward_coef` 从 0.5 提高到 0.7。
- N2 18DOF 转向单脚支撑奖励权重从 0.25 提高到 0.5。
- N2 18DOF 速度课程上限从 3.0 提高到 3.5，门限同步调到 0.70。

验证：
- `python3 -m py_compile` 检查本次修改相关 Python 文件。
- `git diff --check` 与 `git diff --cached --check`。

追溯：`git show 3bd6c3cc7a2877738ad14d05492f18f8ff139b4e`

## 2026-07-14 09:54:07 +0800 - a020a62dd368e780b0e84f195d91ea7f8646796c

标题：支持 N2 RGMT play 导出关节顺序

简要：
- `scripts/rsl_rl/play.py` 为 `WalkRun-N2-AMP-RGMT-History-18DOF` 增加 N2 18DOF 部署关节顺序映射。
- 使该 RGMT 任务在 play/export 时能使用正确的 deployment joint names。

验证：
- `python3 -m py_compile scripts/rsl_rl/play.py`
- `git diff --check` 与 `git diff --cached --check`。

追溯：`git show a020a62dd368e780b0e84f195d91ea7f8646796c`

## 2026-07-13 11:37:06 +0800 - 82b55c6648c0730f2fb0e25e0ea78a8efe0127b1

标题：调整 N2 WalkRun 转向与后退训练

简要：
- N2 速度命令采样增加纯 yaw、纯后退样本，并记录 stand/forward/backward/pure_yaw 等命令比例指标。
- 新增横向速度独立跟踪、前向欠速、yaw L2 跟踪和 yaw 欠速惩罚。
- 单脚支撑奖励支持按 yaw 命令阈值启用，转向时降低默认关节偏差约束。
- 10DOF/18DOF WalkRun 配置接入上述命令采样和奖励项，并降低 action rate 惩罚。
- 18DOF 额外增加上肢关节偏差和站立手臂约束。

验证：
- `python3 -m py_compile` 检查本次修改的 4 个 Python 文件。
- `git diff --check` 与 `git diff --cached --check`。

追溯：`git show 82b55c6648c0730f2fb0e25e0ea78a8efe0127b1`

## 2026-07-13 11:07:11 +0800 - 95452be92563241b2fbc7eb53dabbe2d7ca84648

标题：新增 N2 WalkRun AMP 数据集

简要：
- 新增 N2 18DOF WalkRun AMP TXT motion 数据集，共 20 条。
- 覆盖站立、前进走路、合成后退、原地左右转、行进转弯、慢/中/快跑等类别。
- 数据位于 `source/NoetixN2/NoetixN2/assets/datasets/walkrun/n2_18dof/`。

追溯：`git show 95452be92563241b2fbc7eb53dabbe2d7ca84648`

## 2026-07-13 11:06:47 +0800 - 06e895558d7092678d3e7a29ec4db6a82cd974ea

标题：新增 N2 AMP motion 转换工具

简要：
- 新增 `scripts/motion/n2_pkl_to_amp.py`，用于将 N2 18DOF PKL motion 转为 AMP TXT/JSON 格式。
- 增加 `stable_walkrun` 预设，支持走跑、转向、合成后退和站立 motion 输出。
- `play_animation.py` 注册 NoetixN2 tasks，可直接播放 N2 AMP motion。
- 更新 motion README，补充 N2 转换和播放命令。

验证：
- `python3 -m py_compile scripts/motion/n2_pkl_to_amp.py scripts/motion/play_animation.py`

追溯：`git show 06e895558d7092678d3e7a29ec4db6a82cd974ea`

## 2026-07-13 11:06:24 +0800 - f2b7b9368f17defe49344df747fe2e317ca0cc78

标题：修复精确环境安装流程

简要：
- `install-exact.sh` 支持 `RESUME_EXISTING=1` 继续未完成的虚拟环境安装。
- 安装 lock 依赖前先固定安装 `setuptools==80.9.0` 和 `wheel==0.45.1`。
- pip 安装 lock 文件时增加 `--no-build-isolation`，避免 `flatdict==4.0.1` 构建时缺少 `pkg_resources`。
- README 补充对应手动安装和恢复安装说明。

追溯：`git show f2b7b9368f17defe49344df747fe2e317ca0cc78`

## 2026-07-10 20:52:11 +0800 - c6f68771a7a2fb0e07265bd3a89da68ea84bb5ba

标题：增加 E1 转向单脚支撑奖励

简要：
- 扩展 `feet_air_time_positive_biped`，支持通过 `command_name` 选择速度命令，并可用 `min_yaw_command` 限定奖励仅在转向命令达到阈值时生效。
- 保留原有默认行为：不配置 `min_yaw_command` 时，仍对任意非零平移或转向命令计算单脚支撑奖励。
- 在 E1 23DOF 和 24DOF WalkRun 配置中新增 `feet_air_time_turning`，权重为 0.25，阈值为 0.4，仅在 `|yaw command| > 0.2` 时启用。

验证：
- `python3 -m compileall -q` 检查本次修改的 3 个 Python 文件。
- `git diff --check` 与 `git diff --cached --check`。
- 结果：以上检查均通过。

追溯：`git show c6f68771a7a2fb0e07265bd3a89da68ea84bb5ba`


## 2026-07-10 20:28:01 +0800 - ad647c56fd8e427c23b4136d1857e8952d84ba44

标题：新增 E1/N2 RGMT 训练与 N2 Mimic 资产

简要：
- 新增 RGMT history encoder，并接入 HIM actor-critic、estimator 和 E1/N2 WalkRun agent 配置。
- 注册 E1 23DOF/24DOF 与 N2 18DOF RGMT WalkRun 任务，同时保留原有 MLP 配置作为默认策略。
- 完善 ONNX exporter、play 和 Sim2Sim 的部署关节顺序、metadata 与 RGMT attention opset 支持。
- 新增 N2 PKL-to-NPZ 转换和 Mimic motion 回放工具，并提交四个 N2 18DOF Mimic 运行时 NPZ 资产。
- 更新 N2 URDF、机器人配置、Mimic motion 校验和 WalkRun/Mimic 相关配置。
- 调整 `.gitignore`，允许跟踪 motion 工具、N2 处理后 NPZ 和 `rsl_rl/tests`，继续忽略 raw motion、`walkrun_full`、日志和生成目录。
- 新增 RGMT encoder、HIM/RGMT 集成与部署顺序 wrapper 测试。

验证：
- `.venv/bin/python -m pytest -q rsl_rl/tests`
- 结果：13 passed，6 subtests passed；仅有 ONNX tracing/deprecation warnings，无失败。

追溯：`git show ad647c56fd8e427c23b4136d1857e8952d84ba44`


## 2026-07-10 14:28:59 +0800 - 57b1f305e28e979d83505c782204ee8faeb23783

标题：清理 N2 数据占位并忽略旧资产

简要：
- 删除 N2 mimic/walkrun 数据目录中已不再需要的 `.gitkeep` 占位文件。
- `.gitignore` 新增忽略 `assets/robots/n2_old/`，旧版 N2 资产备份不进入 Git。
- 清空本次相关暂存区，无关 RGMT/rsl_rl/mimic 改动仍保留在工作区未提交。

追溯：`git show 57b1f305e28e979d83505c782204ee8faeb23783`

## 2026-07-10 14:23:08 +0800 - 4075fe21014d1293cfa8afd11354f3e9f55afd3e

标题：更新 N2 URDF 机器人资产

简要：
- 更新 N2 `n2.urdf`，碰撞模型改为 mesh，并调整部分惯量、关节限位和力矩/速度参数。
- 替换 N2 STL mesh，文件体积明显减小。
- 新增统一 `mjcf/n2.xml`，删除旧 `n2_10dof.xml` 和 `n2_18dof.xml`。
- 移除旧 `urdf/n2_10dof.urdf`，保留/更新统一 N2 URDF 资产。

追溯：`git show 4075fe21014d1293cfa8afd11354f3e9f55afd3e`

## 2026-07-09 18:51:20 +0800 - 2ed0a56198593f1530e7cb38abf79dc5feaeb52f

标题：忽略 motion 生成文件

简要：
- `.gitignore` 新增忽略 `scripts/motion/`。
- 忽略 N2 mimic raw 数据、mimic NPZ 输出和 `walkrun_full/` 数据目录。
- 目的：motion 转换脚本和生成数据先保留在本地，不进入后续 commit。

追溯：`git show 2ed0a56198593f1530e7cb38abf79dc5feaeb52f`

## 2026-07-09 18:48:07 +0800 - 6f95ca7e4ec0c881624bfa37eb9987cf2b0436be

标题：更新 WalkRun 课程与配置

简要：
- 更新 E1/N2 WalkRun 课程逻辑，增加窗口统计和 curriculum 指标记录。
- 调整 E1/N2 WalkRun 速度课程参数，初始前向速度上限调到 1.5。
- 补充 `reward_gate_ratio`、`required_successes` 等课程配置。
- E1 WalkRun 命令/奖励相关逻辑同步调整。

备注：
- motion/mimic 数据、脚本和数据集占位变更未纳入本次 commit。

追溯：`git show 6f95ca7e4ec0c881624bfa37eb9987cf2b0436be`



## 2026-07-09 11:30:26 +0800 - 2413d5e4df6b72a5d2686abe7651fbec1904916b

标题：调整 E1 WalkRun 命令课程

简要：
- UniformVelocityWithZeroCommand 增加命令类型统计：stand、forward、backward、pure_yaw、lateral、forward_yaw、mixed。
- 新增 pure yaw 命令采样参数 rel_pure_yaw_envs 和 pure_yaw_min_abs，用于单独提高原地转向样本比例。
- lin_vel_cmd_levels 改为窗口累计评估，满足前向样本数、奖励阈值和 x 速度相对误差后，连续成功多次才提升最大前向速度。
- E1 23DOF/24DOF WalkRun 配置降低 action_rate_l2 惩罚权重到 -0.05，并设置 window_reset_samples=2048。
- 23DOF AMP runner 将 amp_reward_coef 从 0.5 提高到 0.7。

后续追溯：git show 2413d5e4df6b72a5d2686abe7651fbec1904916b

## 2026-07-08 17:41:51 +0800 - 24c305245547c6b62c2ff1c366c4a192ce5156e5

标题：调整 E1 WalkRun 速度奖励

简要：
- 在 E1 WalkRun rewards 中新增横向速度独立跟踪奖励 track_lin_vel_y_yaw_frame_exp。
- 新增高速前向命令欠速惩罚 lin_x_undershoot_penalty，用于惩罚实际 x 速度明显低于命令速度的情况。
- 新增 yaw 角速度 L2 惩罚 track_ang_vel_z_world_l2，避免只依赖指数型跟踪奖励饱和。
- joint_deviation_l1 在转向命令较大时关闭惩罚，减少转向动作被默认姿态约束压制。
- E1 23DOF/24DOF WalkRun 配置接入上述奖励项，并分别设置权重。
- .gitignore 新增忽略 rewards_update.py，避免临时调参文件进入 Git。

后续追溯：git show 24c305245547c6b62c2ff1c366c4a192ce5156e5

## 2026-07-07 - 增加 N2 sim2sim 入口和导出关节顺序

提交标题：

```text
Add N2 sim2sim launch scripts
```

简要：

- 新增 N2 WalkRun 10DOF sim2sim 入口脚本。
- 新增 N2 WalkRun 18DOF sim2sim 入口脚本。
- 新增 N2 Mimic 18DOF sim2sim 入口脚本。
- `play.py` 增加 N2 10DOF/18DOF 的部署关节顺序映射，用于 ONNX 导出和 metadata。
- 主要用途：方便直接用 N2 MJCF 跑 Mujoco sim2sim，并让 N2 WalkRun 导出的 ONNX 关节顺序可追溯。

## 2026-07-07 - 打包 NoetixN2 资产并约束 Mimic 关节

提交标题：

```text
Package NoetixN2 assets and constrain mimic joints
```

简要：

- `NoetixN2/setup.py` 改为使用 `find_packages`，避免只安装顶层包。
- 安装包增加 N2 URDF、MJCF、STL mesh 和 dataset 目录。
- N2 Mimic 的 action、event、reward 关节选择从宽泛正则改为 `N2_18DOF_JOINT_NAMES`。
- 目的：安装后的 NoetixN2 包能找到必要资产，并让 Mimic 逻辑只作用在预期的 18DOF 关节上。

## 2026-07-06 - 增加 N2 Mimic 18DOF 任务

提交标题：

```text
Add N2 Mimic 18DOF task
```

简要：

- 新增 `Mimic-N2-18DOF` Gym 注册。
- 新增 N2 Mimic tracking env、config、agent 模块。
- 新增 Mimic MDP 组件：motion command loader、observations、rewards、events、curriculum、terminations。
- 新增 `assets/datasets/mimic/n2_18dof/.gitkeep`，作为 motion `.npz` 数据目录占位。
- `NoetixN2.tasks` 在轻量 Python 工具导入时允许缺少 `isaaclab_tasks`。
- 后续：训练前需要补入真实 `yinggewu_18dof.npz` motion 文件。

## 2026-07-06 - 增加 N2 WalkRun AMP 任务

提交标题：

```text
Add N2 WalkRun AMP tasks
```

简要：

- 新增 `WalkRun-N2-AMP-10DOF` 和 `WalkRun-N2-AMP-18DOF` Gym 注册。
- 新增 N2 WalkRun AMP env、config、agent、MDP 模块。
- 新增 `n2_10dof` 和 `n2_18dof` 数据集占位目录。
- 新增 N2 symmetry、rewards、events、commands、observations、curriculum hooks。
- 新增 `AmpJsonMotionLoader` 别名，并让 discriminator mask 使用通用 motion loader 名称。
- 后续：训练前需要把真实 AMP JSON motion 文件放到 N2 数据集目录。

## 2026-07-06 - 注册 Noetix N2 extension 框架

提交标题：

```text
Register Noetix N2 extension scaffold
```

简要：

- 新增 NoetixN2 包框架：`__init__.py`、`setup.py`、`pyproject.toml`、`config/extension.toml`。
- 新增 N2 manager helper，用于手动 action term 和历史 observation flatten。
- 新增 `NoetixN2/terrains/` terrain generator preset。
- 在 `train.py`、`play.py`、`list_envs.py` 中导入 `NoetixN2.tasks`。
- 更新 `pyrightconfig.json`，让工具识别 `source/NoetixN2`。
- 后续：需要继续补充具体 N2 task config。

## 2026-07-06 - 增加 Noetix N2 机器人资产

提交标题：

```text
Add Noetix N2 robot assets
```

简要：

- 新增 `source/NoetixN2/NoetixN2/assets/robots/n2/`。
- 包含 N2 Isaac Lab articulation 配置 `n2.py`。
- 包含 18DOF 和 10DOF 的 URDF/MJCF。
- 包含 base、arm、leg 相关 STL mesh。
- 后续：如果需要训练或仿真入口，需要继续接入 N2 task/import path。

## 2026-07-01 - `c3a904e82620a4d720c6456645b5f967ed6cae8f`

提交标题：

```text
Support deployment joint order in ONNX export
```

### 目的

让导出的 WalkRun E1 ONNX policy 兼容 CTRL_E1Base 的部署关节顺序。

修改前，训练 policy 的 action/order 来自 Isaac Lab action term。如果真实部署控制器使用不同关节顺序，导出的 ONNX 模型和 metadata 可能与部署侧不一致。本次提交在导出时增加 wrapper：输入 observation 中的关节字段先从部署顺序重排到 policy 顺序，policy 输出 action 后再重排回部署顺序。

### 文件变更

#### `.gitignore`

新增忽略本地/生成文件：

- `report/`
- `constraints-isaacsim-*.txt`

回滚影响：

- 只影响 Git 跟踪规则。
- 不影响训练、仿真、导出运行逻辑。

#### `pyrightconfig.json`

新增 Pyright 配置：

- 包含 `source/NoetixE1`、`rsl_rl/rsl_rl`、`scripts`。
- 增加 Isaac Lab / Isaac Sim 相关 `extraPaths`。
- 使用较宽松的 type checking 配置，关闭或降低部分诊断。

回滚影响：

- 只影响编辑器和静态分析。
- 不影响运行时。

#### `rsl_rl/pyproject.toml`

license 元数据从：

```toml
license = "BSD-3-Clause"
```

改为：

```toml
license = { text = "BSD-3-Clause" }
```

回滚影响：

- 只影响 packaging metadata。
- 不影响运行时。

#### `source/NoetixE1/NoetixE1/assets/robots/e1/e1.py`

新增部署关节顺序常量：

- `E1_23DOF_CTRL_POLICY_JOINT_NAMES`
- `E1_24DOF_CTRL_POLICY_JOINT_NAMES`

说明：

- 23DOF 顺序显式列出，用于 CTRL_E1Base 部署。
- 24DOF 当前复用 `E1_24DOF_JOINT_NAMES`，因为部署顺序目前与 Isaac Lab action 顺序一致。

回滚影响：

- 如果删除这些常量，需要同步调整 `scripts/rsl_rl/play.py` 的 import 和使用。
- 只回滚该文件而保留 `play.py` 改动，会导致 play/export 导入失败。

#### `scripts/rsl_rl/play.py`

新增 WalkRun 任务的部署关节顺序查找：

- `WalkRun-E1-AMP-23DOF` -> `E1_23DOF_CTRL_POLICY_JOINT_NAMES`
- `WalkRun-E1-AMP-24DOF` -> `E1_24DOF_CTRL_POLICY_JOINT_NAMES`

ONNX 导出路径变更：

- 从 `env.unwrapped.action_manager.get_term("joint_pos")._joint_names` 读取 policy 关节顺序。
- 将 policy 和 deployment 关节顺序传入 `export_policy_as_onnx`。
- 将 deployment 关节顺序传入 `attach_onnx_metadata`。
- 导出时打印部署顺序 wrapper / metadata 的提示信息。

回滚影响：

- ONNX 导出会回到直接使用 Isaac Lab action 顺序。
- metadata 不再强制写入 CTRL_E1Base 部署顺序。
- 如果部署侧仍期待 CTRL_E1Base 顺序，可能重新出现关节顺序不匹配。

#### `rsl_rl/rsl_rl/utils/exporter.py`

主要功能变更：

- 新增关节名校验 helper：
  - `_check_joint_name_set`
  - `_joint_order_indices`
- 新增 WalkRun observation layout 推断：
  - `_infer_walkrun_obs_layout`
- 扩展 `export_policy_as_onnx` 参数：
  - `policy_joint_names`
  - `deployment_joint_names`
- 增加 `_OnnxPolicyExporter.input_size` 解析，让 wrapped export 能拿到 ONNX input size。
- 新增 `_WalkRunDeploymentOrderPolicyWrapper`。
- 扩展 `attach_onnx_metadata`，增加可选 `joint_names` 参数。
- 新增 `_action_scale_to_list`，按指定关节顺序导出 action scale。
- 写 metadata 前先清空旧 metadata。

部署 wrapper 行为：

- 只支持非 recurrent 的 flat WalkRun policy。
- 根据 input size 和 joint count 推断 stacked observation layout。
- 支持 WalkRun observation frame 结构：
  - base observation fields
  - joint positions
  - joint velocities
  - previous actions
- 推理前将 joint position、joint velocity、previous action 从部署顺序重排到 policy 顺序。
- policy 输出后再把 action 从 policy 顺序重排回部署顺序。

metadata 行为：

- 如果传入 `joint_names`，metadata 按该顺序写入。
- 使用 `robot.find_joints(..., preserve_order=True)` 将指定关节名映射到 robot data index。
- 按 action term 的关节顺序重排 `action_scale`。

回滚影响：

- 这是核心功能改动。
- 回滚该文件会移除部署顺序 ONNX wrapper 和有序 metadata 导出。
- `scripts/rsl_rl/play.py` 也需要同步回滚或调整，因为它依赖新的 exporter 参数。

### 验证

提交前运行：

```bash
git diff --check
python3 -m compileall rsl_rl/rsl_rl/utils/exporter.py scripts/rsl_rl/play.py source/NoetixE1/NoetixE1/assets/robots/e1/e1.py
```

结果：

- `git diff --check` 通过。
- `python3 -m compileall` 通过。
- 未运行完整 Isaac Lab export/play。

备注：

- `python -m compileall ...` 失败，因为当前 shell 没有 `python` 命令。
- 改用 `python3` 后通过。

### 后续排查

查看提交：

```bash
git show c3a904e82620a4d720c6456645b5f967ed6cae8f
```

查看改动文件：

```bash
git show --name-only --format=fuller c3a904e82620a4d720c6456645b5f967ed6cae8f
```

检查当前导出的 ONNX 是否带有部署顺序 metadata：

```bash
python3 - <<'PY'
import onnx

model = onnx.load("path/to/exported/policy.onnx")
for item in model.metadata_props:
    print(item.key, item.value)
PY
```

23DOF 可与下列常量对比：

```python
from NoetixE1.assets.robots.e1.e1 import E1_23DOF_CTRL_POLICY_JOINT_NAMES
```

### 回滚方式

推荐安全回滚：

```bash
git revert c3a904e82620a4d720c6456645b5f967ed6cae8f
```

该命令会新建一个反向提交，保留历史。

如果手动回滚，需要注意依赖关系：

- `scripts/rsl_rl/play.py` 依赖 `e1.py` 中新增的常量。
- `scripts/rsl_rl/play.py` 依赖 `export_policy_as_onnx` 的新参数。
- `scripts/rsl_rl/play.py` 依赖 `attach_onnx_metadata` 的 `joint_names` 参数。
- 只回滚 `exporter.py` 而不回滚 `play.py`，会破坏 ONNX 导出。
- 只回滚 `e1.py` 而不回滚 `play.py`，会破坏 import。

### 风险备注

- wrapper 通过 input size 推断 WalkRun observation layout。未来如果 WalkRun observation 形状变化，`_infer_walkrun_obs_layout` 可能报错，或错误重排字段。
- recurrent policy 明确不支持该部署顺序 wrapper。
- 非 WalkRun 任务不受影响，除非主动传入 `deployment_joint_names`。
- 24DOF 当前假设 CTRL_E1Base 部署顺序与 Isaac Lab action 顺序一致。

## 2026-07-01 - 更新 E1 23DOF motion 数据集

提交标题：

```text
Update E1 23DOF motion datasets
```

### 目的

更新 WalkRun 和 Mimic 实验使用的 E1 23DOF motion 数据，并避免临时 motion 工作目录进入 Git。

### 文件变更

#### `.gitignore`

新增临时目录忽略规则：

- `temp/`
- `**/temp/`

作用：防止本地 motion 临时文件被误提交。

#### WalkRun 23DOF motion 数据

目录：

```text
source/NoetixE1/NoetixE1/assets/datasets/walkrun/e1_23dof/
```

删除旧 running motion：

- `e1_running_forward.txt`
- `e1_running_turn.txt`

新增 running motion：

- `e1_running_fast_4p8.txt`
- `e1_running_slow_2p8.txt`

更新已有 motion：

- `e1_sidewalk.txt`
- `e1_standing.txt`
- `e1_turning.txt`
- `e1_walk_backward.txt`
- `e1_walk_forward.txt`

验证：

- 已提交的 WalkRun motion txt 均可解析为 JSON。
- 检查到的 WalkRun frame 维度为 `133`。
- 检查到的 WalkRun 文件包含 `23` 个 joint names 和 `24` 个 key body names。

### Mimic 23DOF motion 数据

新增：

```text
source/NoetixE1/NoetixE1/assets/datasets/mimic/e1_23dof/fast_test.npz
```

验证：

- NPZ 可以正常打开。
- 包含 key：
  - `fps`
  - `joint_pos`
  - `joint_vel`
  - `body_pos_w`
  - `body_quat_w`
  - `body_lin_vel_w`
  - `body_ang_vel_w`
- `joint_pos` 和 `joint_vel` 形状为 `(4249, 23)`。

### 后续排查

该提交修改了较大的 motion 资产。如果训练表现变化，优先对比：

- motion sampling weights
- root velocity 和 root height
- joint range 和 joint velocity range
- WalkRun txt 中的 contact mask
- 被删除的 running motions 是否仍被某些实验脚本引用

常用命令：

```bash
git show --stat HEAD
git show --name-status HEAD
```

### 回滚方式

推荐安全回滚：

```bash
git revert HEAD
```

如果之后再回滚，把 `HEAD` 替换为本次 motion 数据更新的实际 commit hash。

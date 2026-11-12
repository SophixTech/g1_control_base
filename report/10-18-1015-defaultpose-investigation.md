# 1015 首帧 state 与 Reset 默认位姿调查

日期：2026-10-18

## 1. 数据与维度

本次“1015”指 /home/bjtc/Sophix/datasets/datav2_1015_split。

取 train/data/chunk-000/file-000.parquet 中 `episode_index=0`、`frame_index=0`、`timestamp=0` 的 `observation.state`。

源 episode：df1f339e-41c1-4568-9de3-cc5e28fd4f8e（`source_episode_index=0`）。

state 为 16 维 float32：0～6 左臂七关节、7～13 右臂七关节（单位 rad），14、15 为左右夹爪反馈。

准确说是 14 个手臂关节 + 2 个夹爪位置量，不是 16 个旋转关节；没有头、腰、升降或底盘信息。

## 2. 1015 首帧实际数值（未归一化的原始 observation.state）

```text
左臂：[-1.52532196, 0.57450634, 1.41524732, -0.59884912, 0.15228616, 1.33651304, 0.02633205]
右臂：[1.62743938, -0.68540108, -0.52835107, 0.29338685, -1.30026925, -1.27016807, -0.48488316]
夹爪：[0.00000000, 0.00000000]
```

0922 对照：/home/bjtc/Sophix/datasets/marked_9_1_0922/train/data/chunk-000/file-000.parquet，同样取 episode=0/frame=0。

```text
左臂：[-1.00358558, 0.56551713, 0.27298781, -1.20502722, 0.68243712, 1.39926684, -0.17631727]
右臂：[1.07423699, -0.61104661, -0.27947795, 1.28383505, -0.73037100, -1.49546123, 0.18758750]
夹爪：[0.00000000, 0.21733333]
```

两条首帧的手臂最大绝对差为 1.142260 rad，不能混用默认姿态。

夹爪 state 是反馈量，不能一概当成 SDK 的 0～1 命令。1015 此首帧两夹爪均为 0，可对应现有 Open=0 预设；0922 的 0.21733333 不应直接解释成 21.7% 闭合。当前配置右夹爪 Default=0.0018111083（约为该反馈 /120）。

## 3. 首帧不是整个数据集唯一的 defaultpose

扫描 train+test 所有 episode 的 `frame_index=0`：1015 共 502 条，只有 1 条与上述参考的全部 14 关节均相差不超过 0.05 rad；最大单关节差为 1.405056 rad。

0922 共 1055 条，214 条在其首条参考的 0.05 rad 范围内，也不是所有首帧完全相同。

因此可把指定 episode 首帧定义为测试用 defaultpose，但不能声称这是全体 1015 的统一采集起始姿态；不建议未经确认直接取所有首帧均值当 Reset 目标。

## 4. 当前 Reset 到底用什么

网页 Reset → web_client/server.py:_client_control_reset → robot.reset_robot(mode='default') → client/robots/base_robot.py:reset_robot。

它读取正在使用的 YAML 中 `robots.agibot_g1.action_layout` 下各部位的 presets.Default，并不从模型权重或数据集首帧自动加载。

具体路径：

| 部位 | 配置路径 | 值 |
| --- | --- | --- |
| 双臂 | `arm.presets.left.Default` / `arm.presets.right.Default` | 各 7 个 rad 数值 |
| 夹爪 | `gripper.presets.left.Default` / `gripper.presets.right.Default` | 各 1 个 SDK 命令值 |
| 其他部位 | `head.presets.Default` / `waist.presets.Default` / `wheel.presets.Default` | 对应部位预设 |

目前 conf/lingbot_newarti_package.yaml 的默认手臂仍接近 0922：例如左臂前三项 [-1.003602, 0.565485, 0.273005]，并不是上述 1015 首帧。

Reset 会暂停控制、执行预设并保持暂停；不是只重置模型，也不只移动双臂。

## 5. 不同模型切换建议（本次只调查，未修改位姿）

保留两份完整客户端 YAML，例如 lingbot_newarti_0922.yaml 与 lingbot_newarti_1015.yaml。

0922 配置保留经过验证的 Default；1015 配置将双臂 Default 改为第 2 节选定首帧，夹爪为 [0,0]。

1015 state 没有头/腰/升降信息：这些位姿必须另从该批采集配置或原始记录确认，不能由 16 维 state 推导；未确认前不要宣称已恢复 1015 的完整全身 defaultpose。

切换模型时同时切换客户端 YAML，停止当前控制并重启/重建客户端机器人实例，保证子进程加载了新的预设；仅换模型服务或编辑磁盘 YAML 不会自动切换已创建实例的 Reset 目标。

当前 scripts/run_lingbot_newarti_g1_client.sh 在参数末尾固定 --conf lingbot_newarti_package.yaml，直接追加另一个 --conf 不适合作为切换方式。可绕过该封装，明确启动：

```bash
source hardware/g1/g1_pc_gdk_env.sh
.venv/bin/python run_web_client.py --host 127.0.0.1 --port 9000 --conf lingbot_newarti_1015.yaml
```

（先准备对应完整配置；0922 时换另一文件。未创建这两个示例配置。）

后续若做网页 pose profile 选择，应让 0922/1015 的完整 Default 配置同步到 RobotProxy 子进程，再执行 Reset；只改变网页显示的预设名称是不够的。

## 6. 实际切换指南：改哪个文件、用哪组初始化

### 6.1 修改正在启动的客户端配置

**Defaultpose 由 Open-RAIL 客户端 YAML 决定，修改哪个文件取决于启动脚本。** 配置目录为 `/home/bjtc/Sophix/g1-open-rail/conf/`。

| 使用的启动脚本（`scripts/` 下） | 应修改的配置文件（`conf/` 下） |
| --- | --- |
| `run_lingbot_newarti_g1_client.sh` | [lingbot_newarti_package.yaml](../conf/lingbot_newarti_package.yaml) |
| `run_lingbot_ori_g1_client.sh` | [lingbot_ori_package.yaml](../conf/lingbot_ori_package.yaml) |
| `run_lingbot_ecot_g1_client.sh` | [lingbot_ecot_package.yaml](../conf/lingbot_ecot_package.yaml) |
| `run_lingbot_g1_client.sh` | [lingbot_package.yaml](../conf/lingbot_package.yaml) |

例如使用 ORI 模型的客户端脚本时，应修改 `conf/lingbot_ori_package.yaml`；只修改 NEWARTI 配置不会影响该客户端。自行运行 `run_web_client.py` 时，以实际 `--conf` 指定的文件为准。

在该文件的 **`robots.agibot_g1.action_layout`** 下修改这四个字段，保留其他字段、`Custom` 和其他机器人配置：

```text
arm.presets.left.Default
arm.presets.right.Default
gripper.presets.left.Default
gripper.presets.right.Default
```

### 6.2 数据与初始化的对应关系

| 测试数据 / 场景 | 选择的初始化 | 说明 |
| --- | --- | --- |
| `marked_9_1_0922` 对应场景 | 下方「0922 初始化」 | 保留当前 NEWARTI 的既有预设，其双臂数值接近 0922 首条首帧。 |
| `datav2_1015_split` 对应场景 | 下方「1015 初始化」 | 采用本报告第 2 节指定 episode 的首帧双臂值；这是选定的测试参考姿态。 |
| 对上述数据仅执行 `crop_1016.py` 图像裁剪 | 沿用裁剪前数据对应的初始化 | 裁剪不改变 `state/action`；裁剪配置与位姿配置分别选择。 |
| 同时用 0922、1015 训练的混合模型 | 根据本次测试场景选择 | 一个 checkpoint 不自动对应唯一 defaultpose，不能只依据模型名决定。 |

以下代码块是**四个字段的取值清单**，点号表示 YAML 嵌套路径。请替换已有字段的数组，不要把点号路径当作新键追加，也不要用清单覆盖整个配置文件。

**0922 初始化：沿用当前 NEWARTI 配置值。** 与第 2 节原始首帧有微小差别，恢复既有预设时用这一组。

```text
arm.presets.left.Default = [-1.003602, 0.565485, 0.273005, -1.204992, 0.682469, 1.399298, -0.176315]
arm.presets.right.Default = [1.074222, -0.611064, -0.279427, 1.283814, -0.730387, -1.49543, 0.187605]
gripper.presets.left.Default = [0.0]
gripper.presets.right.Default = [0.0018111083333333332]
```

**1015 初始化：本次选定首帧的双臂姿态，左右夹爪采用 Open=0。**

```text
arm.presets.left.Default = [-1.52532196, 0.57450634, 1.41524732, -0.59884912, 0.15228616, 1.33651304, 0.02633205]
arm.presets.right.Default = [1.62743938, -0.68540108, -0.52835107, 0.29338685, -1.30026925, -1.27016807, -0.48488316]
gripper.presets.left.Default = [0.0]
gripper.presets.right.Default = [0.0]
```

双臂单位为 rad；夹爪这里填写的是 SDK 命令值。尤其不要将 0922 的原始右夹爪反馈 `0.21733333` 直接填入命令预设。

**头、腰和升降的 1015 初始化仍需另行确认。** 当前 NEWARTI 配置的 `head.presets.Default` 为 `[-0.257285, 0.42817]`，`waist.presets.Default` 为 `[0.491126, 44.752]`，`wheel.presets.Default` 为 `[0, 0]`。这些只是当前配置值，并非从 1015 的 16 维 state 得到的对应位姿。Reset 会使用这些部位的预设，因此仅替换上述四项不能称为完整全身位姿匹配。

### 6.3 修改后如何生效

1. 停止 Control，并退出对应的客户端进程；先备份其完整 YAML。
2. 在该 YAML 中替换上述四个 `Default` 数组，并核对其他部位预设。
3. 重新运行原客户端启动脚本，让机器人实例加载新配置；模型权重按本次测试任务另行选择。
4. 确认机器人运动空间允许复位后，在网页执行 **Reset**；核对双臂到达所选姿态。Reset 后仍处于暂停状态，需要继续推理时再执行 Control Start。

仅刷新网页、切换模型服务器或修改磁盘上的 YAML，都不能保证已创建的机器人实例加载新 Default。这里的初始化指 **Reset 的目标姿态**，不是修改文件后机器人立即运动。

如果经常切换，建议按第 5 节保存两份完整配置；配置名称应对应实际使用的客户端，例如 ORI 可命名为 `lingbot_ori_0922.yaml` / `lingbot_ori_1015.yaml`，从 `conf/lingbot_ori_package.yaml` 复制后修改。通过 `run_web_client.py --conf 文件名` 明确选择；启动时沿用原脚本所需的环境和端口。以上备用配置尚未创建，本次只补充文档，未修改运行配置或下发机器人动作。

## 调查依据

两个数据集的 meta/info.json、episode_mapping.jsonl 和实际 Parquet；convert_datav2_1015.py:aligned_numeric；client/robots/base_robot.py:reset_robot；client/robots/agibot_g1/body_robot.py:execute_action；web_client/server.py:_client_control_reset；当前 NEWARTI YAML。

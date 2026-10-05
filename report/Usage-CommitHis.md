# 提交历史记录

## 2026-10-05 部署速查与当前配置整理

### d1a634ebde7b00bcff63cac415c9db8e0680d8a7

时间：2026-10-05 17:38:04 +0800
标题：`chore(deploy): simplify LingBot quickstart and save current configuration`

用途：简化部署操作文档，并保存已有工作区配置及报告管理调整。

- `README-LingBot-G1.md`：改为按终端和操作顺序组织的部署速查；列出可复制启动命令、模型权重与统计文件路径、chunk 长度、去噪次数、网页操作、退出及日志查看方式。保留现有编辑内容。
- `conf/lingbot_package.yaml`：保存已有修改，`controller.speed` 从 0.5 改为 1.0，`intra_chunk.intra_chunk_mode` 从 `interpolation` 改为 `fitting`。这些会改变运行行为，不是已经验证的轨迹偏离修复。
- `.gitignore`：增加 `/reports/`。
- 移除 Git 中的 `reports/openrail_action_pipeline_20261003.md` 与 `reports/chunk55_reconstruction.svg`；对应文件已在本地 `report/` 中，本次未将被忽略的报告批量重新纳入 Git。
- 验证：README 的 7 个 Bash 命令块通过 `bash -n`（仅语法检查）；YAML 解析通过；清理文档行尾空格后 `git diff --check` 通过。
- 未运行模型、未连接真机、未修改跨块融合算法，也未对当前倍率和 fitting 配置做真机验收。

本次历史文档同时保留已有的报告链接调整，指向本地 `report/` 中的文件；新克隆仓库不包含这些被忽略的报告。历史记录另以 `docs(history): record deployment quickstart and configuration commit` 提交，其哈希可通过 `git log -- report/Usage-CommitHis.md` 查询。


## 2026-10-04 按功能整理本次未提交改动

本批次将已有工作区改动拆为五个功能提交，下面按最新提交在前排列。没有实现新的跨块融合算法，没有将异步改成串行，也没有启动模型或连接真机。已有测试目录移除暂存项一并归入清理提交。

### ce780317f918c6e7ad5cf922a3f1ce518fd610d7

时间：2026-10-04 16:12:07 +0800
标题：`docs(control): explain asynchronous fusion and recorded trajectory deviations`

用途：说明模型位置经过客户端处理后，为什么会与最终提交目标产生较大偏离。

- 文件：[动作链路与 min_jerk 计算教程](openrail_action_pipeline_20261003.md)、[chunk 55 重建图](chunk55_reconstruction.svg)。
- 内容包括 30 Hz 与约 267 Hz、两次导数计算、旧块与新块的接入索引、过渡曲线公式、日志证据和读图方法。
- 保留分析结果和图；临时数值计算 Python 脚本、JSON 及缓存已清理，它们此前未纳入 Git，因此没有删除记录。
- 验证：文档本地链接存在，重建图随文档提交；未把文字中的改进建议实现为控制代码。

### dcf1d9c0b941b395e6da0805a5e20f62d2a97d94

时间：2026-10-04 16:12:01 +0800
标题：`chore(config): save LingBot execution speed at 0.5`

用途：保存当前工作区已有的 LingBot 运行倍率配置。

- 文件：`conf/lingbot_package.yaml`。
- 唯一变化：`controller.speed` 从 0.3 改为 0.5。
- 异步模式、3.75 ms 控制周期、块内插值和 min_jerk 配置保持原样。
- 这不是已经验证的异常动作修复，也不是位置、速度或加速度硬限制。单独提交便于追踪这项运行配置。

### 3cc9c109afe1adf0b2fab41b32c38b3228d669e9

时间：2026-10-04 16:11:52 +0800
标题：`feat(diagnostics): trace G1 joint commands and render offline reports`

用途：把同一个模型块的原始目标、客户端提交、SDK 调用和关节反馈关联起来，并离线可视化。

主要文件：

- `client/core/joint_trace.py`：通过有界队列异步写日志，并记录丢失数量。
- `client/core/vla_client.py`、`client/core/realtime_data_manager.py`：记录模型块、控制点和执行时间，保持块 ID 与当前轨迹对应。
- `client/robots/robot_proxy.py`、`client/robots/agibot_g1/body_robot.py`：透传诊断上下文，记录 SDK 目标、队列丢弃和反馈。
- `run_web_client.py`：增加 `--trace-joint` 和 `--trace-dir` 参数。
- `scripts/analyze_joint_trace.py`：生成无需联网的 HTML、CSV 和统计结果。
- `README-LingBot-G1.md`：诊断功能的使用方式与证据限制。

使用方法：从仓库根目录，在操作者准备启动客户端时执行：

```bash
scripts/run_lingbot_g1_client.sh --host 127.0.0.1 --port 9000 --trace-joint 8
```

索引 0～6 是左臂，7～13 是右臂；8 表示右臂第二关节。不传 `--trace-joint` 则关闭诊断。日志默认放在 `logs/joint_traces/<会话目录>/`，可以通过 `--trace-dir` 改根目录。

结束采集后，生成离线报告：

```bash
python3 scripts/analyze_joint_trace.py logs/joint_traces/<会话目录>
```

输出为 `report.html`、`commands.csv`、`feedback.csv`、`summary.json`。用浏览器打开 HTML。原始预测参考是线性连接；反馈按 PC 读取时刻显示。SDK 返回不代表电机已经执行，规划导数不是真机实测导数。

验证：Python 语法检查通过；日志写入和关闭刷新检查通过；用 19:15 会话的 28496 条事件完成真实日志解析与 HTML 内存渲染。未操作机器人。

### 3cdb676115e239caa341e97bd8d4c8801e1a5540

时间：2026-10-04 16:11:41 +0800
标题：`fix(client): serialize lifecycle cleanup and preserve occupied ports`

用途：避免客户端创建与关闭并发冲突，并修复可视化服务关闭方式。

- `web_client/server.py`：串行协调组件创建与清理；关闭开始后阻止新建组件；清理异常时记录错误并尝试关闭机器人代理。
- `client/core/visualize_server.py`：通过事件循环的线程安全接口发送退出信号。
- `run_web_client.py`、可视化服务：端口被占用时由绑定失败报告错误，不再自动强制杀死端口占用进程。
- 无新增操作参数。验证了 Python 语法；本环境未完成生命周期回归测试。

### 26c45b9aa497e35a5e5ba693215378f308395db3

时间：2026-10-04 16:11:25 +0800
标题：`chore(repo): stop tracking local tests and generated logs`

用途：整理版本管理范围，避免纳入本地测试资料和运行生成数据。

- `.gitignore` 增加 `/test/` 和 `/logs/`。
- 提交此前已经暂存的 11 个 `test/` 文件移除项，包含观测样本、Notebook 和测试脚本。当前本地仍存在的被忽略文件不等于它们仍被 Git 跟踪。
- 原始真机日志仍留在本地，不在提交中。日志采集和可视化代码继续跟踪。
- 没有删除生产控制模块，也没有回退现有诊断功能。

### 本批次验证范围

- `git diff --check` 与各次暂存差异检查通过。
- 修改的 Python 文件及新日志模块、报告脚本通过语法编译检查。
- 日志写入关闭刷新、真实日志解析与 HTML 渲染通过。
- 尝试运行诊断、生命周期、代理控制和启停相关 pytest 用例，但项目 `.venv` 报告 `No module named pytest`；这些回归测试本次未运行，不能记为通过。
- 未运行模型推理、未连接真机、未验证修改后的真机性能；没有新的融合算法改动。

本历史文档原先位于被忽略的 `report/` 目录。本次只将本文件显式纳入 Git，保留下方旧记录；其他报告目录内容未批量添加。本批次另有一个仅保存此历史文档的提交，可用 `git log -- report/Usage-CommitHis.md` 查询其哈希。

## 2026-10-03 14:31:24 +0800 - 6c19414e4bf5b88c9dfe2a23507bd23442ddc990

标题：完成 M07 控制启停接入

- 开始／恢复前采样左夹爪；重复开始不重采样，准备失败不启用。
- 离线测试 82 项通过、1 项跳过，未连接机器人或加载模型。

## 2026-10-03 14:29:01 +0800 - a47d3a13af8211da4a6b1c3a93400958ab21ab7b

标题：完成 M06 G1 控制迁移

- 双臂绝对目标；左夹爪保持，右夹爪四次方处理。
- 增加执行前状态检查，保留夹爪发送间隔。
- 离线测试 71 项通过、1 项跳过，未连接机器人或加载模型。

## 2026-10-03 14:21:55 +0800 - c0f933c895ebdd5124af64752bd3957eab3eb611

标题：完成 M05 G1 图像与状态适配

简要：

- 按同一图像包的格式解码，修正原始 RGB 颜色转换。
- 修复首帧状态拼接丢值，保留原始夹爪反馈与时间对齐。

验证：

- 新增 9 项离线测试通过；合并 M03 共 35 项通过、1 项跳过。
- 未连接机器人或加载模型。

追溯：`git show c0f933c895ebdd5124af64752bd3957eab3eb611`

## 2026-10-03 13:57:33 +0800 - 1dda0174dd8daf44026eb1a88c79978120de011c

标题：完成 M04 本地 G1 环境与客户端启动入口

简要：

- 将 G1 环境准备迁入本仓库，新增 uv 安装脚本，使用本地 Python 3.10 `.venv`。
- 新增软包任务客户端启动脚本及环境说明，保留厂家底层目录引用。

验证：

- 47 个包依赖检查、客户端及 SDK 导入、脚本离线检查通过。
- 未加载 GPU 模型或操作机器人；完整启动待 M08 配置。

追溯：`git show 1dda0174dd8daf44026eb1a88c79978120de011c`

## 2026-10-03 13:45:56 +0800 - 6e3ebb6b500cd1e07af19f658381b1cb5c8ca634

标题：新增 M03 LingBot 适配器测试

简要：

- 新增 25 / 50 步接口测试，覆盖观测映射、动作输出与必要的错配检查。
- 提供显式启用的真实观测推理测试入口，默认跳过。

验证：

- 26 项假模型测试通过，1 项真实推理测试跳过。
- 按用户要求暂缓 GPU 推理，避免影响训练。

追溯：`git show 6e3ebb6b500cd1e07af19f658381b1cb5c8ca634`

## 2026-10-03 13:39:15 +0800 - ab472cff79df44916e2ec26f0add946779ac5212

标题：完成 M02 LingBot 服务入口与启动脚本

简要：

- `run_server.py` 接入 LingBot 参数覆盖，支持 25 / 50 步，推理线程设为 1。
- 新增 `scripts/run_lingbot_server.sh`，使用模型环境启动 ZMQ 服务。
- 本机模型环境补齐 `ml-collections==1.1.0`、`pyzmq==27.2.0`（环境安装不在提交内）。

验证：

- 9 项测试、Python/Bash 语法及 Git 差异检查通过。
- 真实环境 `--help` 可用；尚未加载真实权重或验证真机。

追溯：`git show ab472cff79df44916e2ec26f0add946779ac5212`

## 2026-10-03 13:18:25 +0800 - 1b33b6b3fd65dd342f44e67ac11ea7ee6efc267e

标题：完成 M01 LingBot 模型适配，支持 25 / 50 步配置

简要：

- 新增 LingBot 适配器及导出入口，完成观测映射和动作返回。
- 新增模型配置，支持权重、统计文件、动作步数和去噪步数设置。
- `.gitignore` 加入 `/report/`。

验证：

- 13 项测试、Python 语法及 Git 差异检查通过。
- 未加载真实权重；完整配置导入和真机验证尚未完成。

追溯：`git show 1b33b6b3fd65dd342f44e67ac11ea7ee6efc267e`

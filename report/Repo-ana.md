# Open-RAIL 部署闭环代码分轮阅读报告

本文是一份可以打开源码逐轮跟读的路线图。每轮只安排 **2～3 个关键文件**，大型文件按函数分段阅读；配置、工具和测试放在同轮的辅助阅读中。主线从模型返回动作开始，经过轨迹处理、G1 执行、图像与状态采集，最后回到下一次模型推理。

**先明确最重要的一点：模型不直接给 G1 电机发指令。模型返回一个动作块，客户端把动作块转换成可执行轨迹，另一个控制循环逐点提交目标；相机和关节反馈始终通过独立观测链路采集，再被后续推理使用。** 这是并行运行的闭环，不是一条执行完动作才拍照的串行函数调用链。

分析日期为 2026-10-02，依据当前仓库 `39f8b91482381d446b08dff804836e8eaff1260e` 的代码。机器人指智元精灵 G1/G01；下文“G1 执行”指机器人本体执行，不是说 Open-RAIL 必须调用相邻 `g1` 仓库的 Python 脚本。本报告只做本地源码阅读，没有启动 Web 服务、模型服务或机器人连接，也没有修改运行代码。

## 1 阅读范围和整个闭环

### 1.1 本文选择的具体路径

为避免同时追踪十几个模型，本文用默认注册的 **GR00T N1.5 适配器**讲清模型端，机器人端选择 `agibot_g1`。实际使用哪个模型，以 `run_server.py` 参数及最终配置为准；默认模型路径仍是占位值，有适配代码不等于当前环境已经具备可用 checkpoint。

模型无关的部分包括 ZMQ 协议、客户端调度、轨迹处理、机器人代理和观测回传。若以后换成 OpenPI、ACT 或其他模型，主要替换模型适配器的阅读，闭环主体仍然适用。当前仓库没有直接注册 LingBot-VLA，不能把相邻 `g1` 工程的 WebSocket 8006 协议当成本仓库模型接口。

### 1.2 闭环总图

```text
模型服务进程
  ModelVLA.infer → Gr00tPolicy.get_action
       ↓ 返回 pred_action[T, D]
  VLAServer.inference_callback → ZMQServer 发送队列
       ↓ ZMQ 模型通信，默认 5566
客户端主进程
  ZMQClient → VLAClient._request_inference
       ↓
  RealtimeDataManager 原始动作
       ↓
  IntraChunkSmoother 块内拟合或插值
       ↓
  InterChunkFuser 块间衔接
       ↓
  RealtimeDataManager 当前可执行轨迹
       ↓ 控制定时器逐点提取
  RobotProxy.control_robot → 跨进程动作队列
       ↓
机器人工作进程
  _RobotWorker._control_loop → RobotBody.control_robot
       ↓
  a2d_sdk.RobotDds → 厂家通信 → Orin 运控 → G1 执行器
       ↓ 真实反馈持续产生
  RobotBody.retrieve_observation
       ↓ 头相机参考帧 + 最近时刻双腕图像和本体状态
  共享内存图像 + 观测队列
       ↓
客户端主进程
  RobotProxy.retrieve_observation
       ↓
  VLAClient 采集线程 → 本地观测队列 → 图像处理线程
       ↓ resize、JPEG 编码、任务文本
  RealtimeDataManager 观测缓冲 → 推理线程取观测
       ↓ ZMQ 请求
模型服务进程
  VLAServer 解码 → ModelVLA.infer → 下一段动作
```

图中的各段可以同时工作：GPU 计算新动作时，机器人可以执行旧轨迹；机器人执行时，相机也在采集新图像。新动作到达后替换后续计划，并不要求先完整执行旧块。

### 1.3 十轮阅读清单

| 轮次 | 本轮解决的问题 | 关键文件数量 | 关键文件 |
| --- | --- | --- | --- |
| 1 | 组件从哪里启动和组装 | 3 | `run_server.py`、`run_web_client.py`、`web_client/server.py` |
| 2 | 模型如何生成并返回动作 | 3 | `server/core/vla_server.py`、`server/models/gr00t/gr00t_n1_5.py`、`server/core/zmq_server.py` |
| 3 | 客户端如何认领响应并建立动作时间轴 | 2 | `client/core/zmq_client.py`、`client/core/vla_client.py` |
| 4 | 动作块如何变成连续轨迹 | 3 | `realtime_data_manager.py`、`intra_chunk_smoother.py`、`inter_chunk_fuser.py` |
| 5 | 控制线程如何把目标交给机器人进程 | 3 | `vla_client.py`、`client/utils/multi_thread_timer.py`、`client/robots/robot_proxy.py` |
| 6 | G1 如何解释动作并调用 SDK | 3 | `client/robots/agibot_g1/body_robot.py`、`client/robots/base_robot.py`、`conf/robots_conf.py` |
| 7 | 反馈如何采集并跨进程回传 | 3 | `body_robot.py`、`robot_proxy.py`、`client/core/shared_memory_manager.py` |
| 8 | 反馈如何变成下一次模型输入 | 3 | `vla_client.py`、`realtime_data_manager.py`、`task_language_manager.py` |
| 9 | 暂停、恢复、复位如何改变闭环 | 3 | `web_client/server.py`、`vla_client.py`、`robot_proxy.py` |
| 10 | 数据记录与可视化究竟记录了什么 | 3 | `data_record_manager.py`、`lerobot_dataset_recorder.py`、`visualize_server.py` |

第 4、8、10 轮中省略目录前缀的文件都在 `client/core/`。重复出现的文件不是要求重读全文，而是分轮读不同职责的函数。

建议按表顺序阅读。如果希望按程序第一次启动后的真实时间顺序追踪，则是第 1 轮 → 第 6、7、8 轮先产生观测 → 第 2、3、4、5 轮产生首批目标 → 再回到第 7、8 轮。

## 2 第一轮 组装部署进程

**关键文件：** [run_server.py](/home/bjtc/Sophix/g1-open-rail/run_server.py:12)、[run_web_client.py](/home/bjtc/Sophix/g1-open-rail/run_web_client.py:1)、[web_client/server.py](/home/bjtc/Sophix/g1-open-rail/web_client/server.py:77)。

**本轮只读这些函数：**

| 文件 | 阅读顺序 |
| --- | --- |
| `run_server.py` | `parse_args` → `override_config_with_args` → `get_model` → `main` |
| `run_web_client.py` | `parse_args` → `main`，同时看模块顶部的线程相关设置 |
| `web_client/server.py` | `_lifespan` → `_ensure_vla_client_created` → `_create_robot` → `_start_client` → `/api/client/start` |

服务端创建顺序是 `ZMQServer → ModelVLA → VLAServer`。模型实例由 `get_model()` 按 `ModelType` 延迟导入，模型网络和权重不由客户端持有。`VLAServer.run()` 放到后台线程运行，主线程主要维护终端显示和退出处理。

Web 入口启动 Uvicorn，设置 `conf_file`，由 FastAPI lifespan 读取 Python 默认配置，再叠加存在的 YAML。Web 服务启动时不等于已经启动机器人闭环；`_ensure_vla_client_created()` 才构造 RobotProxy、ZMQClient、RDM、两类轨迹处理器、语言管理器和 VLAClient。

这里的 `_create_robot()` 返回的是 **RobotProxy**，真实 `RobotBody` 和厂家 SDK 在工作子进程里构造。不要看到 `vla_client.robot` 就以为它一定是 SDK 实例。

`/api/client/start` 返回“starting”时后台任务可能仍在初始化。它最终调用 `VLAClient.start()`，该方法依次开启观测、推理、控制和可视化。因此“Start client”不应被理解为纯只读预览；观测、推理和控制也有独立 API。

**辅助阅读放在本轮：** [客户端配置](./conf/client_conf.py)、[服务端配置](./conf/server_conf.py)、[模型配置](./conf/models_conf.py)、[通信配置](./conf/zmq_conf.py)。前端 HTML、CSS 和终端布局暂时跳过。

先记住以下默认值，后面逐项解释：

| 参数 | 默认值 | 实际含义 |
| --- | --- | --- |
| 模型类型 | GR00T N1.5 | 服务端默认分支，可由 CLI 覆盖 |
| 机器人类型 | agibot_g1 | 客户端选择的具体机器人适配器 |
| 模型 ZMQ 端口 | 5566 | 观测和动作通信 |
| Web 端口 | 9000 | 操作界面 REST 和 `/ws` 状态推送 |
| 可视化 WebSocket | 8765 | 图像和轨迹展示，不是模型推理通道 |
| `rdm.mode` | async | 推理不等待旧动作块播放完成 |
| `raw_fps` | 30 | 训练动作时间轴频率，不直接设定相机硬件 FPS |
| `controller.period` | 3.75 ms | 上层控制回调名义间隔 |

**本轮应能回答：** 模型在哪个进程？SDK 在哪个进程？点击启动后谁创建谁？哪些端口承载模型输入，哪些只给浏览器使用？

## 3 第二轮 模型生成动作并返回

**关键文件：** [vla_server.py](/home/bjtc/Sophix/g1-open-rail/server/core/vla_server.py:140)、[gr00t_n1_5.py](/home/bjtc/Sophix/g1-open-rail/server/models/gr00t/gr00t_n1_5.py:10)、[zmq_server.py](/home/bjtc/Sophix/g1-open-rail/server/core/zmq_server.py:126)。

**阅读顺序：**

1. `VLAServer.recvThreadFun()` 接收一个带 client ID 的请求。
2. `VLAServer.inference()` 解码图像，把模型任务提交给线程池。
3. `ModelVLA.__init__()` 理解状态切片和模型配置，再读 `infer()`。
4. `VLAServer.inference_callback()` 包装结果。
5. `ZMQServer.sendMessage()` 和 `_sender_worker()` 把结果真正送出去。

### 3.1 模型适配器做了哪些转换

GR00T 适配器从 checkpoint 的 `experiment_cfg/metadata.json` 读取状态模态的维度，按 metadata 的迭代顺序建立连续切片。接到 state 后加一个前导维度，再切成 `state.*` 各模态。

图像与语言的映射为：

| 框架字段 | GR00T 输入字段 |
| --- | --- |
| `obs['cam.head']` | `video.cam_top_head` |
| `obs['cam.hand_left']` | `video.cam_left_wrist` |
| `obs['cam.hand_right']` | `video.cam_right_wrist` |
| `obs['state']` | 由 metadata 定义的多个 `state.*` 切片 |
| `obs['language']` | `annotation.human.task_description` |

真正模型调用是 `self.policy.get_action(inp_obs)`。归一化、模型网络与具体 transform 主要在外部 GR00T 包中；这里不能只读十几行适配代码就认定已理解模型全部预处理。

输出若包含 `prob_progress`，先取出放到 `ext`；其他动作数组按字典 values 的顺序拼接到列维，形成 `[T,D]`。**输出字典顺序必须与机器人 action layout 一致**，当前代码不是根据 `left_arm/right_arm` 名字重新排序。输入 metadata 顺序也需要与 RobotBody 拼接 state 的顺序匹配。

T 是模型动作块长度，不是仓库全局固定的 50。D 对当前默认 G1 模型动作布局通常为 16，实际仍需检查 checkpoint 输出。

### 3.2 返回消息长什么样

```python
# 模型适配器返回的数据体
{
    'type': 'vla_action',
    'pred_action': action_array,  # [T, D]
    'ref_timestamp': original_ref_timestamp,
    'loc_timestamp': original_client_timestamp,
    'ext': {'prob_progress': optional_progress},
}

# 通信层 metadata，单独编码
{
    'request_id': original_request_id,
    'avg_infer_time': smoothed_server_elapsed_seconds,
}
```

`ref_timestamp` 和 `loc_timestamp` 从输入回传，不是动作实际执行时间，也不是服务端生成的时间戳。`avg_infer_time` 从图像解码结束之后计到回调执行，可能包含线程池等待，不能直接叫纯 GPU kernel 时间。

### 3.3 ZMQ 实际发送过程

服务端 ROUTER 收到的 multipart 为 `[client_id, pickle(data), JSON(meta)]`，返回时也带 client ID 用于路由。`sendMessage()` 只是把消息放进容量默认 1000 的发送队列；独立 `_sender_worker()` 再序列化并发送。入队成功不等于客户端已经收到，发送队列满时结果会被丢弃。

默认有 3 个推理 worker、9 个解码 worker。多个 worker 可以同时调用同一个模型对象，实际模型是否适合并发、显存及吞吐如何，需要单独测量；线程数不等于推理速度倍数。

**建议观察的变量：** `inp_obs` 各键形状、metadata 状态顺序、`predicted_action` 各分量名与形状、拼接后 `[T,D]`、client ID、request ID。

**本轮应能回答：** 哪一行真正调用模型？模型输出如何变成统一动作块？怎样保证第 0～6 维真的是左臂？返回动作有没有直接发布到 G1？

## 4 第三轮 客户端接收动作和建立时间轴

**关键文件：** [zmq_client.py](/home/bjtc/Sophix/g1-open-rail/client/core/zmq_client.py:195)、[vla_client.py](/home/bjtc/Sophix/g1-open-rail/client/core/vla_client.py:635)。

本轮只读 VLAClient 的 `_request_inference()`、`_inference_first()`、`_inference_step()`、`_process_action_chunk()` 和 `_parse_prob_progress()`；暂不展开观测线程和控制线程。

### 4.1 一次请求如何匹配一次响应

`_request_inference()` 分配 request ID，通过 `ZMQClient.sendMessage(data, meta)` 发出。ZMQ 数据体用 pickle，metadata 用 JSON；图像在此之前已经编码成 JPEG/PNG，`memoryview` 在序列化边界转换为可 pickle 的值。

`recvMessage()` 返回 `{'data': ..., 'meta': ...}`。VLAClient 只接受 request ID 匹配的结果，旧响应会被丢弃。普通请求默认超时 500 ms，首次请求使用 4 倍，即 2000 ms。客户端模型 DEALER 与 heartbeat DEALER 是两个 socket，避免心跳消息与动作结果共用同一路正常通信。

**超时不是取消 GPU 推理。** 客户端不再等待后，服务端可能仍在计算并最终返回旧结果；request ID 用于把它识别出来。心跳正常也只说明服务能够响应心跳，不能证明某个推理按时完成。

### 4.2 首轮和后续轮的区别

| 步骤 | `_inference_first()` | `_inference_step()` |
| --- | --- | --- |
| 观测来源 | RDM 中取最新观测 | 同样取最新观测 |
| 请求超时 | 默认 2000 ms | 默认 500 ms |
| 原始动作组织 | 建立初始动作与参考标记 | 替换新原始动作 |
| 块内处理 | 有 | 有 |
| 跨块融合起点 | 没有旧轨迹，传入 `None` | 取 RDM 旧命令轨迹的位置、速度、加速度 |
| 最终安装 | 安装首份可执行轨迹 | 替换后续可执行轨迹 |

初始轨迹并没有自动从机器人实测初始姿态规划一段 Ruckig 过渡。Ruckig 在手动控制路径中，不能因仓库里有该函数，就认为首轮模型动作自动经过它。

### 4.3 原始动作时间轴

`set_observe_period()` 定义：

```text
observe_period = 1 / controller.speed / controller.raw_fps
```

默认 speed=1、raw_fps=30，因此原始动作间隔是 1/30 秒。尽管名字里有 observe，它主要决定动作块的回放时间尺度，并非相机采集线程的 sleep 周期。

`_process_action_chunk()` 为每个 action 建立相对时间 `index × observe_period`，但会把列表第一个元素临时写成 `ref_timestamp`。随后 RDM 的 `update_action_chunk_raw()` 又把第一个时间元素重置为 0。所以到轨迹处理层时，真正使用的是从 0 开始的相对秒时间轴。不要把中间这个混合列表直接拿来当作全为纳秒或全为秒的最终时间戳。

`loc_timestamp` 独立保存在 `observe_marker`，用于估计本次动作已经“老了多久”。它由客户端生成，往返模型服务后仍是同一个数值。

**建议观察：** `request_id`、结果形状、`observe_period`、`timestamp_chunk` 在调用 RDM 前后的变化、`loc_timestamp`。

**本轮应能回答：** 过期响应为什么不会被误认为新响应？训练 30 FPS 怎样变成动作时间？第一次推理与后续推理哪里不同？

## 5 第四轮 动作块变成可执行轨迹

**关键文件：** [realtime_data_manager.py](/home/bjtc/Sophix/g1-open-rail/client/core/realtime_data_manager.py:195)、[intra_chunk_smoother.py](/home/bjtc/Sophix/g1-open-rail/client/core/intra_chunk_smoother.py:41)、[inter_chunk_fuser.py](/home/bjtc/Sophix/g1-open-rail/client/core/inter_chunk_fuser.py:22)。

**辅助配置：** `conf/client_conf.py` 中 `get_intra_chunk_config()`、`get_inter_chunk_config()`、`get_controller_config()`；`client/utils/util.py` 的 `parse_action_layout()`。

建议在纸上记录三个变量：`原始动作 [T,D]`、`拟合轨迹 [D,M]`、`当前执行索引 k`。它们贯穿本轮。

### 5.1 RDM 如何存动作

`update_action_chunk_raw()` 把动作转成 float32 并转置：`[T,D] → [D,T]`。每行对应一个关节或夹爪维度，每列是一个时间点。

`pop_action_chunk(time_offset=0)` 根据时间轴选出用于拟合的数据，但函数内部当前时间仍写成 0，并不是在此实现完整的实时过期裁剪。真正的延迟相关起始索引在后面的 `get_start_chunk_index()` 中计算。

### 5.2 块内处理做什么

`IntraChunkSmoother.process()` 把 `time_step` 从毫秒换成秒，再按模式分支：

| 模式 | 阅读函数 | 意义 |
| --- | --- | --- |
| raw | `_traj_raw` | 查看保留原始动作的基线行为 |
| interpolation | `_traj_interpolation` | 对时间轴重采样 |
| fitting 默认 | `_traj_fitting` | 按 action layout 对不同维度使用不同处理 |

默认 G1 双臂是 `gradual`：`_joint_traj_fitting_batch()` 用 Vandermonde 矩阵和最小二乘拟合，默认四阶多项式；再对新时间网格求位置、一阶导数、二阶导数。它是对整段动作的近似拟合，未必逐点穿过模型输出，也可能改变局部细节。

默认夹爪是 `stepwise`，但并非原样阶跃输出：它做滑动均值，窗口默认 `2×4+1=9` 个原始点，再用 0.05/0.95 阈值吸附到全开/全闭，之后在新网格上组合相邻值。当前分支输出的夹爪速度和加速度置零。这说明它把夹爪当作与手臂不同的语义通道。

新时间网格是 `np.arange(start_time, end_time, dt)`，通常不含末端点。例如仅用于说明的 `[50,16]` 块，以 30 FPS 和 3.75 ms 重采样，会得到约 436 列 `[16,436]` 轨迹，时间覆盖原始第 0 到第 49 点之前的网格。增加发布点数没有让模型多推理，也不是提高视觉闭环频率。

### 5.3 如何决定从新轨迹哪里开始

`get_start_chunk_index()` 计算：

```text
time_offset = 开始块间处理的客户端时刻 - 输入观测的 loc_timestamp
```

然后找到新轨迹中第一个大于该偏移的时间点，作为候选起点。它包含从观测处理时刻到推理返回及块内处理的开销，但不完整包含后续融合、队列和 SDK 延迟，也不等于相机曝光至电机执行的端到端时延。

注意两个边界：若所有点都已早于 time_offset，当前函数仍可能返回默认 0；首轮安装时由于旧 `action_chunk_index` 是 None，也会从初始索引开始，而不是完全按计算出的延迟索引播放。

### 5.4 块间融合做什么

后续推理先调用 `RDM.get_current_state()` 取旧轨迹当前位置、速度、加速度，再交给 `InterChunkFuser.process()`。**这里的 current state 是命令轨迹状态，不是 G1 HAL 实测关节。** 这是理解平滑效果的关键。

| 模式 | 当前主要实现 | 跟读重点 |
| --- | --- | --- |
| search_action | `_search_smooth_action` | 向新块前方搜索较合适接点，会改变采用的索引 |
| smooth_velocity | `_smooth_velocity_transition_numba` | 按速度和加速度约束构造跟随式过渡 |
| min_jerk 默认 | `_min_jerk_chunk_transition_numpy` | 用旧轨迹边界条件构造五次过渡，并与目标尾部混合 |
| sync | 直接使用下一轨迹 | 此处只是融合算法选择，不等同于 rdm.mode 的同步推理调度 |

min_jerk 默认根据位置、速度、加速度差估计过渡长度。由于尾部还与原目标位置混合，不能仅凭名称就认为每个接缝严格具有最优或受限 jerk。它平滑的是命令轨迹，也没有证明实际机械反馈始终跟得上。

### 5.5 安装轨迹与夹爪提前量

`update_action_chunk_fitted()` 最终安装位置、速度、加速度、时间轴和任务进度，并设置执行索引。动作字段在同一个 `action_lock` 下成组替换，避免控制线程看到新旧数组混搭。

安装前 `_apply_gripper_offset()` 对 stepwise 维度做移位。默认 `gripper_offset=5` 是**拟合后轨迹的 5 列**，在默认 3.75 ms 下约为 18.75 ms，不是 5 个训练帧的 166.7 ms。正值把后面的夹爪值提前放到前面的时刻；末尾未覆盖部分保留原值。

**本轮应能回答：** 为什么形状转置？块内和块间分别解决什么？融合的 current state 来自哪里？夹爪提前量到底以什么为单位？

## 6 第五轮 控制循环与机器人代理

**关键文件：** [vla_client.py](/home/bjtc/Sophix/g1-open-rail/client/core/vla_client.py:553)、[multi_thread_timer.py](/home/bjtc/Sophix/g1-open-rail/client/utils/multi_thread_timer.py:6)、[robot_proxy.py](/home/bjtc/Sophix/g1-open-rail/client/robots/robot_proxy.py:609)。

这次回到 VLAClient，只读 `_control_thread_fun()`、`start_control()`、`stop_control()`。在 Proxy 中读 `control_robot()`、`_RobotWorker._control_loop()` 和 `_handle_command()`。

### 6.1 谁按频率触发执行

VLAClient 构造 `MultiThreadTimer(period, _control_thread_fun)`。定时器是单线程循环，不会每一帧无限创建新线程。每轮回调后计算本轮耗时，再等待 `max(0, period-elapsed)`。

默认 3.75 ms 对应名义 266.7 Hz，但 Python、系统调度、锁、IPC 和 SDK 都会影响实际执行频率。回调超时就没有 sleep；不能把配置值当成机器人实际收包频率。

`_control_thread_fun()` 在控制开启时：

```text
获取 _control_execution_lock
  → RDM.get_action_fitted()
  → RobotProxy.control_robot(action_fitted)
释放锁
  → 提交录制动作
  → 更新任务进度
  → 更新可视化
```

控制回调里虽然没有 GPU 推理，但仍有锁和侧路工作，不是纯粹的硬实时发布器。

### 6.2 索引怎样前进

`get_action_fitted()` 每调用一次就把索引加一并钳制到末列，不是每次用单调时钟重新计算位置。若实际回调慢于配置，轨迹播放时间会被拉长；到末列以后则持续返回末目标。

一个容易忽略的细节是它“先加索引，再取值”：首轮初始索引通常是 0，第一次取得的常常是第 1 列。可视化模式也能推进索引；从 visualize 切到 control 时会把索引归零后再推进。读代码时不要默认它严格按 `0,1,2,...` 发送整个数组。

### 6.3 为什么使用非阻塞 Proxy

`RobotProxy.control_robot()` 复制当前目标，将 `(epoch, action_snapshot)` 放到跨进程队列，立即返回。它检查进程是否存活及是否出现后台控制错误，但不等待机器人完成执行。

工作进程的 `_control_loop()` 有自己的线程：收到一个动作后尽可能读完当前队列，选择最新项，获取机器人命令锁，核对 epoch，再调用真实 `RobotBody.control_robot()`。这避免相机读取拖住每一条连续控制命令，也避免堆积的旧轨迹逐点慢慢补发。

**“只执行最新项”不等于队列容量为 1。** 当前 `_control_queue` 本身没有设置 maxsize，最新值策略在消费端实现；消费者持续阻塞时仍需考虑内存积压。被合并的点没有真正执行，短暂夹爪事件也可能被合并。

### 6.4 连续控制和手动 RPC 是两条路

| 路径 | API | 行为 |
| --- | --- | --- |
| 模型连续控制 | `control_robot()` | 本地复制、异步入队、不等回执、消费端合并 |
| 手动或复位 | `execute_action()`、`_control_robot()`、`reset_robot()` | `_rpc()` 带命令 ID 请求，等待远端结果 |

两者都使用工作进程的 `_robot_command_lock` 串行化真实命令调用。长时间手动规划会影响连续控制线程取得锁；互斥调用不等于完整的“人或模型二选一”任务控制权管理。

**本轮应能回答：** 266.7 Hz 是谁的频率？Proxy 返回意味着什么？最新值在哪里合并？为什么不能把控制调用数当成实际执行点数？

## 7 第六轮 G1 动作布局与 SDK 调用

**关键文件：** [body_robot.py](/home/bjtc/Sophix/g1-open-rail/client/robots/agibot_g1/body_robot.py:58)、[base_robot.py](/home/bjtc/Sophix/g1-open-rail/client/robots/base_robot.py:20)、[robots_conf.py](/home/bjtc/Sophix/g1-open-rail/conf/robots_conf.py:27)。

阅读 `get_agibot_g1_config()` → `RobotBase.__init__()` → `RobotBody.control_robot()` → `execute_action()`。手动分支最后再读 `_control_robot()` 与 `ruckig_planning()`。

### 7.1 动作维度与观测维度不是一回事

| 分段 | 索引 | policy | 默认是否参与模型轨迹处理 |
| --- | --- | --- | --- |
| 双臂 | 0 至 13 | gradual | 是 |
| 双夹爪 | 14 至 15 | stepwise | 是 |
| 头 | 16 至 17 | manual | 否 |
| 腰 | 18 至 19 | manual | 否 |
| 轮式底盘 | 20 至 21 | manual | 否 |

`parse_action_layout()` 排除 manual，所以默认模型 action_dim 是 16；布局最大索引可以达到 22。观测则按 `proprio_names=['arm','gripper','head','waist']` 拼接，在常见 14+2+2+2 返回长度下是 20 维，不含轮子反馈。

因此 `action_dim=16`、实际 `obs.state` 常为 20 维、布局 state_dim=22 可以同时出现。模型适配器必须正确选择所需 state 切片，不能直接让三个维数彼此替代。

### 7.2 模型目标经过哪些处理才到 SDK

双臂切片转成 list 后调用 `execute_action({'arm': ...})`，最后是 `self.robot.move_arm()`。

夹爪在轨迹层已经处理过，到这里还要再经过：

```text
轨迹夹爪值
  → 默认每 40 次 control_robot 调用才处理一次
  → clip 到 [0,1]
  → gamma=4 非线性变换
  → execute_action({hand_type: ...})
  → move_gripper 或相应灵巧手接口
```

非线性公式为 `x^4 / (x^4 + (1-x)^4)`，使靠近 0 和 1 的值更极端。例如 0.3 会变成约 0.033。这是明确改变动作值，不是简单单位换算。

若真实 RobotBody 控制调用达到 266.7 Hz，每 40 次约为 150 ms，即约 6.67 Hz 的夹爪发送频率。若只达到 30 Hz，同样的配置就约为 1.33 s 一次。该计数发生在工作进程真实调用处，不应只按主进程 timer 次数估算。

头部也有分频，但默认 16 维模型动作根本不包含头。`execute_action()` 支持更多部位，不代表模型默认都会控制它们。

### 7.3 SDK 到机器人的边界

本仓库只导入外部 `a2d_sdk`，厂家通信和 Orin 内部控制实现不在这里。当前工作区另有安装的 SDK，可作为辅助核对：

[本地 SDK robot.py](/home/bjtc/Sophix/g1/vendor_packages/a2d_sdk-1.5.0/.venv/lib/python3.10/site-packages/a2d_sdk/robot.py:710)。它的 `move_arm()` 封装关节名称和位置，发布 `/wbc/arm_command`；`move_gripper()` 发布左右 `/wbc/*_ee_command`。Python 层使用厂家 `agibotdds`，不能简单当作 `rclpy` 调用。

实际 Open-RAIL 运行环境可能安装不同 SDK 版本，应核查解释器实际导入路径。`move_arm()` 返回不是“电机到位确认”，不包含本仓库层面的逐点碰撞检测或末端任务完成判断。运控消费位置目标并返回真实关节反馈，才形成下层执行闭环。

### 7.4 手动 Ruckig 不在模型主路径上

`RobotBase._control_robot()` 对手动双臂目标调用 `ruckig_planning()`，构造速度、加速度、jerk 受限的轨迹并逐点调用 `execute_action()`。模型主路径走的是 `RobotBody.control_robot()`，没有自动调用这段 Ruckig。

**本轮应能回答：** 每个维度对应什么？夹爪为什么与模型输出不一样？SDK 调用是什么命令语义？手动轨迹规划是否会保护模型轨迹？

## 8 第七轮 采集反馈和共享内存回传

**关键文件：** [body_robot.py](/home/bjtc/Sophix/g1-open-rail/client/robots/agibot_g1/body_robot.py:130)、[robot_proxy.py](/home/bjtc/Sophix/g1-open-rail/client/robots/robot_proxy.py:202)、[shared_memory_manager.py](/home/bjtc/Sophix/g1-open-rail/client/core/shared_memory_manager.py:91)。

本轮读 `retrieve_observation()`、工作进程 `_loop/_publish/_push_observation`、主进程 `RobotProxy.retrieve_observation()`，最后跟 `encode_observation/decode_observation()`。

### 8.1 观测不是等待动作完成后的回执

机器人工作进程 `_loop()` 持续采集观测，控制在另一个 `_control_loop()` 线程运行。观测没有携带“某动作已完成”的确认，也没有与某一个模型 action 建立严格一一对应关系。它只是采集时附近的图像和实际关节状态。

`RobotBody.retrieve_observation()` 的顺序是：

1. 取参考头相机最新图像及 timestamp。
2. 与上一参考 timestamp 相同则返回 None，避免重复头图像。
3. 用固定线程池，并行取左右腕相机最接近参考时刻的图像。
4. 按 `proprio_names` 顺序取最近时刻本体状态。
5. 拼接 `obs.state`，更新供展示和手动控制使用的 `current_state`。

这是“头图像参考加最近邻配对”，不是多相机硬件同步。非参考图像和状态返回的时间戳在这里没有全部保留，也没有检查最大配对偏差，所以最近邻不意味着时间差一定很小。

### 8.2 两份 state 为什么数值不同

返回给模型的 `result['obs.state']` 是原始拼接值。`current_state` 则会把夹爪部分按 `(raw-35)/(120-35)` 归一化，它被用于前端显示和手动目标等路径。

所以排查夹爪时要明确自己看到的是模型原始反馈、展示 state，还是最终 0 至 1 控制命令。它们不能直接逐维比较，也不能默认采用相邻 `g1` 工程的 raw/120 映射。

### 8.3 图像跨进程怎么传

工作进程给每路相机分配共享内存环形槽，默认 `shm_ring_size=4`。图像数据复制到槽里，跨进程队列主要传小描述符：

```python
{
    'transport': 'shm',
    'name': shared_memory_name,
    'shape': [height, width, channels],
    'dtype': 'uint8',
    'slot_index': slot,
    'timestamp_ns': software_copy_timestamp,
}
```

外层 payload 还携带 `observation`、`current_state` 的副本和 `t_send=perf_counter()`。主进程从描述符打开共享内存并得到 NumPy view，把 `t_send` 作为 `_worker_publish_time` 传给后续处理。

工作进程观测队列默认容量为 2，队满时丢旧保新。主进程 `RobotProxy.retrieve_observation()` 每次只从队列取一项，不会把所有待收观测直接排空到最新项；“取最新观测”是多层机制组合的近似效果。

### 8.4 共享内存的几个细节

- `copy=False` 的解码结果是 view，不是稳定私有图像。环形槽会被生产者复用，长时间持有可能读到后来的帧。
- 描述符的 `timestamp_ns` 在复制时由 `time.time_ns()` 写入，不是相机曝光时间；相机参考时间是另外的 `ref_timestamp`。
- 这里没有逐槽消费确认或严格版本校验，环容量不能被当作无限的保留保证。消费者或录制长期落后时需要检查是否读到被覆盖的槽。
- 主进程 VLAClient 还会建立自己的 30 槽图像池用于本地流水线和录制。这是第二次图像缓冲，不能把整条链称作完全零拷贝。
- 生产者负责 unlink，共享内存读取者只关闭自己的映射缓存；资源归属与普通 Python 对象不同。

**本轮应能回答：** 谁决定一帧是否新？图像和状态如何对时？为什么 IPC 只传描述符？`timestamp_ns` 是否一定是曝光时间？

## 9 第八轮 反馈变成下一次推理输入

**关键文件：** [vla_client.py](/home/bjtc/Sophix/g1-open-rail/client/core/vla_client.py:418)、[realtime_data_manager.py](/home/bjtc/Sophix/g1-open-rail/client/core/realtime_data_manager.py:171)、[task_language_manager.py](/home/bjtc/Sophix/g1-open-rail/client/core/task_language_manager.py:293)。

本轮集中阅读 `_observe_thread_fun()` → `_process_observe_thread_fun()` → `_process_data()` → `_process_image()` → `_inference_thread_fun()`，最后回到第 2、3 轮的网络和模型调用。

### 9.1 三个客户端线程各自负责什么

| 线程 | 主要工作 | 输出 |
| --- | --- | --- |
| observe | 从 RobotProxy 收观测，放入本地图像池和队列 | 本地 FramePacket |
| process_observe | 从共享内存取 view，图像预处理与编码，组装输入 | RDM 中的模型输入 dict |
| inference | 取观测、请求模型、处理新轨迹 | RDM 中新的可执行动作 |

观测队列 `_raw_observe_queue` 容量也为 2，满时实际丢弃最旧项。源码注释中出现“no frame dropping”，与当前实现不一致，跟读时以 `except Full` 分支为准。

### 9.2 图像处理与色彩链

客户端默认预处理为 resize、保持比例、目标 480×640；JPEG quality 默认 80，深度分支使用 PNG。三路图像通过共享线程池并行编码，不是在每一帧临时新建线程池。

普通彩色图像的完整颜色链需要连起来看：RobotBody 做通道反转 → OpenCV 编码 → 服务端 `imdecode(IMREAD_COLOR)` → 服务端再通道反转 → 模型输入。若 SDK 的压缩图像解码输出是 RGB，则 RobotBody 反转为 BGR，编码解码后仍为 BGR，服务端反转回 RGB。

服务端注释 `# RGB to BGR` 不应替代对真实数组语义的判断。SDK 原始图像路径、压缩路径或版本变化都可能改变前提；正确验证方式是在模型真正接收处检查色卡及像素，而不是只看某一处 `[::-1]`。

### 9.3 推理请求具体有哪些字段

```python
{
    'type': 'vla_obs',
    'ref_timestamp': head_camera_timestamp,
    'loc_timestamp': client_perf_counter_seconds,
    'obs': {
        'cam.head': encoded_head_image,
        'cam.hand_left': encoded_left_image,
        'cam.hand_right': encoded_right_image,
        'state': raw_robot_state_array,
        'language': [current_instruction],
    },
}
```

`loc_timestamp` 在 `_process_data()` 开始时生成，在图像编码之前；它没有覆盖相机曝光到进入这个函数之前的所有延迟。模型收到的是压缩图像加状态和语言，不是直接访问 G1 相机，也不是读取 Web 前端画面。

RDM 的 `add_observe_data()` 接受新观测，但首 5 帧不入观测缓冲用于推理。这个 warmup 与 RobotBase 的 FPS 统计 warmup 是两回事：前者影响策略输入，后者主要影响统计。

### 9.4 最新观测与历史观测的实际行为

默认 `pop_observe_data(num_samples=1)` 用 deque 的 `pop()` 取最新一项，但不清空所有更旧项。如果推理比观测快，下一次也可能取到仍留在缓冲里的较旧帧，不能把它理解成“每个请求总能拿到比上次更新的帧”。

`history_frame=True` 时用连续 pop 取两项，返回顺序是新到旧。默认 GR00T N1.5 适配器只使用 `sequence[0]`，所以单独打开该选项并没有让此模型自动使用两帧历史。其他模型适配器是否消费多帧需逐个检查。

### 9.5 新推理何时发生

`_inference_thread_fun()` 根据 `infer_count` 选择首轮或后续轮。完成一轮后调用 RDM `wait_for_next()`：

- 默认 async：等待 `wait_time=10 ms` 后可以进行下一轮，不等旧块完整播放。
- sync：等待当前拟合轨迹索引到达末列，或 clear/reset 等操作打断等待。

所以默认推理频率大致受“观测可用性、请求耗时、轨迹处理耗时、10 ms 等待”共同约束，不是固定 30 Hz，更不是 266.7 Hz。这里没有调用相邻 `g1` 工程的 true RTC 模型空间历史约束。

推理抛出异常时会停止控制、清空 RDM 并退避重试；而 `_request_inference()` 超时返回 None 时，当前 `_inference_step()` 主要是返回并等待下一轮，不走相同的异常清空路径。旧轨迹可能继续到末列并保持，不能把所有“推理失败”视为完全相同的行为。

### 9.6 语言也是闭环的一部分

`TaskLanguageManager` 从任务文件与子任务编号选当前指令。手动语言模式中，`_request_inference()` 在发送前重新写入最新语言，防止队列中早先组装的观测仍带旧指令。

自动语言模式则读取模型返回的 `ext.prob_progress`，经过轨迹进度对齐，由控制回调累计进度、尝试切到下一子任务，再由后续推理结果确认切换。这是依赖模型输出的任务进度机制，不能等同于独立传感器证明抓取或放置完成。

**本轮应能回答：** 下一次推理到底看哪一帧？编码在哪个线程？语言何时更新？async 与 sync 控制的是什么等待条件？

## 10 第九轮 暂停恢复和复位屏障

**关键文件：** [web_client/server.py](/home/bjtc/Sophix/g1-open-rail/web_client/server.py:1455)、[vla_client.py](/home/bjtc/Sophix/g1-open-rail/client/core/vla_client.py:189)、[robot_proxy.py](/home/bjtc/Sophix/g1-open-rail/client/robots/robot_proxy.py:631)。

**辅助阅读：** `realtime_data_manager.py:clear()`，以及 [test_reset_resume_barriers.py](./test/test_reset_resume_barriers.py)、[test_robot_proxy_async_control.py](./test/test_robot_proxy_async_control.py)。本轮可以把测试当成解释具体竞态场景的例子阅读，不需要运行机器人测试。

### 10.1 三种标识分别防什么

| 标识或屏障 | 防止的问题 |
| --- | --- |
| 模型 request ID | 把超时旧请求的响应错认成新请求 |
| RobotProxy control epoch | 暂停或复位前的动作在队列中晚到并继续执行 |
| `_worker_publish_time` 与 RDM reset 时间屏障 | 复位前发布的旧观测经过流水线后又用于新推理 |

它们不是同一个 ID。光检查 request ID，不能解决已经在控制队列里的旧命令；光清控制队列，也不能解决已被取出但正在等锁的旧目标。

### 10.2 暂停动作出口

`stop_control()` 使用 `_control_execution_lock`，关闭主进程提交资格，再调用 `RobotProxy.pause_controls()`；后者禁止新提交、增加 epoch 并清队列。工作线程在取得机器人命令锁之后核对 epoch，过滤之前已出队但尚未进入有效执行的旧动作。

这一机制不能撤回已经开始执行的 SDK 调用，也不等于向厂家发送实体急停。报告中的“暂停”是上层闭环状态，底层实际停止与保持行为仍由机器人控制栈决定。

### 10.3 Web 复位做了什么

`_client_control_reset()` 大致按以下顺序执行：保存原运行线程状态 → 暂停观测、推理与控制 → 通过手动 RPC 归位 → 等待一定时间 → 调用 `VLAClient.reset()` 清理数据 → 保持 paused，等待使用者恢复。

`VLAClient.reset()` 获取 `_inference_execution_lock`，等待当前推理处理段离开后清空 RDM 与原始观测队列。这样，正在返回的旧推理不能在清空之后重新把旧轨迹安装回来。它不是强行取消 GPU 内核。

RDM `clear()` 将 raw 与 fitted 动作字段在一个 action_lock 中同时清空，递增 action generation 并唤醒同步等待；同时记下最小允许观测发布时间，拒绝复位前工作进程发布的观测。

### 10.4 Pause 和 Reset 不能混为一谈

普通 pause/resume 主要切换运行标志和动作队列资格，并不自动等同于“清空全部模型轨迹、重新采集、重新首轮推理”。长暂停后的恢复应特别观察旧 fitted chunk 是否仍保留、在途推理是否已经更新它，以及恢复时索引如何继续。

Web reset 使用 `reset_resume_lock` 串行化复位与恢复任务，但外部 Orin VR 或其他脚本的控制权不由这把锁管理。框架内部不会争用，不等于机器人全系统只有一个控制源。

**本轮应能回答：** 为什么 clear queue 还不够？暂停为何不能取消已经发出的动作？复位后第一帧观测怎样避免来自复位前？

## 11 第十轮 录制和可视化旁路

**关键文件：** [data_record_manager.py](/home/bjtc/Sophix/g1-open-rail/client/core/data_record_manager.py:287)、[lerobot_dataset_recorder.py](/home/bjtc/Sophix/g1-open-rail/client/core/lerobot_dataset_recorder.py:1010)、[visualize_server.py](/home/bjtc/Sophix/g1-open-rail/client/core/visualize_server.py:49)。

**辅助阅读：** `conf/save_conf.py`、`evaluation_result_recorder.py`。网页样式、数据删除与浏览操作可以放在最后，不影响理解动作闭环。

### 11.1 两处数据提交点

VLAClient 的观测处理线程调用 `add_observation_async()`；控制线程在向 Proxy 提交动作后调用 `add_action_async(action_fitted, ...)`。后者拿到的是拟合轨迹目标，**还不是 RobotBody 做完夹爪非线性、分频后的实际 SDK 命令**。

此外 Proxy 可能合并多个连续目标，录制端并不等待硬件执行确认，所以录制 action 不等于“这个点一定发到了 G1”。这对训练数据和控制抖动分析都很重要。

### 11.2 观测与动作如何配对

`_add_action_fun()` 把 action 与软件时间放进缓冲；`_add_observation_fun()` 从动作缓冲 `pop()` 一条最新待配对动作，没有动作就丢弃该观测。当前没有按传感器参考时间去搜索动作时间的最近邻，也不是严格记录“这一图像对应哪一条已执行指令”。

随后配对数据进入录制队列，由常驻写入进程消费，生成视频和 parquet 等文件。名称中的 `async` 不代表调用者完全不做工作：当前两个公开方法直接调用内部提交函数，只是主要磁盘写入在其他进程。

### 11.3 LeRobot 时间戳不是实测控制时间

`_write_frame_fun()` 写出的 parquet `timestamp` 是 `frame_index/30`，采用固定 30 FPS 假设。它适合某种数据集时间轴约定，但不能用来证明真实采样没有抖动或没有丢帧。

录制器还可能对不足的动作或状态维度补零；这说明数据集中的形状不一定是模型实际输出形状。视频输入可能来自共享内存，慢消费者的槽覆盖风险也要结合第 7 轮理解。

### 11.4 可视化与推理不是一条通道

`update_image_data()` 更新供可视化推送的图像，`update_chart_data()` 展示原始动作、拟合动作、速度、加速度和反馈 state。图像和图表会缓存、抽样与发送；浏览器刷新率不代表控制频率，平滑曲线也不直接证明机器人实际运动平滑。

若要排查“模型想做什么”和“G1 真做了什么”，至少需要同时区分四条数据：模型 raw action、拟合后 action、RobotBody 最终 SDK 参数、带真实时间戳的 HAL 反馈。现有旁路没有自动把它们全部记录成逐条可核对的执行回执。

**本轮应能回答：** 录制 action 在夹爪变换前还是后？parquet 的时间来自哪里？图表平滑是否说明电机轨迹平滑？

## 12 把一次完整循环连起来

以下是帮助理解的示例，不是当前 checkpoint 的实测性能。假设模型每次返回 50×16、原始 FPS=30、控制周期 3.75 ms、一次请求及前处理耗时约 0.30 s。

| 顺序 | 事件 | 此时其他模块可能在做什么 |
| --- | --- | --- |
| 1 | 头相机产生新参考帧，RobotBody 配对双腕和状态 | 控制线程仍在执行旧轨迹 |
| 2 | 观测经工作进程共享内存和客户端队列到达图像处理线程 | 新一帧可能已经在相机缓冲中 |
| 3 | 生成 loc_timestamp、编码图像、加入语言、写入 RDM | 旧目标继续被周期性提交 |
| 4 | 推理线程 pop 观测，带 request ID 发送 ZMQ | 采集线程继续更新缓冲 |
| 5 | 服务端解码并调用模型，返回 50×16 动作 | 机器人不会因为 GPU 工作而自动停下 |
| 6 | 客户端认领响应，转成 16×50，拟合成约 16×436 | 控制定时器还在读旧 fitted chunk |
| 7 | 根据 loc_timestamp 年龄选择新轨迹位置，做跨块融合 | 若延迟持续增大，旧轨迹可能到末端保持 |
| 8 | 在 action_lock 下安装新轨迹 | 下次控制回调开始使用新轨迹索引 |
| 9 | Proxy 入队；机器人线程选最新目标，夹爪按分频处理 | 新一轮观测和推理可能已经开始 |
| 10 | SDK 发布，厂家运控跟踪，实际状态持续回传 | 下一次推理使用的是更新的真实观测 |

若新轨迹的时间间隔为 3.75 ms，0.30 s 偏移大约对应第 80 个拟合点附近，而不是第 80 个模型原始动作。该计算只是说明索引量纲；实际 first/step 分支、额外处理开销与先加索引行为都必须按源码核对。

这个循环有两个反馈层：模型隔一段时间根据图像和关节状态重新规划，属于策略层反馈；厂家运控连续跟踪关节目标，属于低层执行反馈。Open-RAIL 的跨块融合主要使用旧命令轨迹，不是自己实现了完整的底层伺服闭环。

## 13 跟读时需要保留的细节清单

### 13.1 数据字段与时钟速查

| 名称 | 来源及单位 | 用途与限制 |
| --- | --- | --- |
| `ref_timestamp` | 头相机 SDK 返回时间，按接口约定为纳秒 | 最近邻观测配对；不一定是已校准的真实曝光起点 |
| `_worker_publish_time` | 工作进程 perf_counter 秒 | reset 观测屏障；不是原始传感器采样时间 |
| `loc_timestamp` | 客户端预处理开始时 perf_counter 秒 | 回传后估计计划年龄 |
| 共享内存 `timestamp_ns` | 复制时 time.time_ns | 软件槽写入时间，不是相机时间 |
| `timestamps_fitted` | 块内相对秒 | 轨迹重采样与新块起点选择 |
| `controller.period` | 配置毫秒 | 定时器与拟合网格，需要显式换成秒 |
| `raw_fps` | 每秒原始动作点数 | 定义模型动作时间语义，不等同推理 FPS |
| `avg_infer_time` | 服务端任务经过时间的平滑统计，秒 | 可能包含队列等待，非纯 GPU 时间 |
| parquet `timestamp` | frame_index/30 秒 | 人工规则时间轴，不是实测发布间隔 |

服务端还使用 `perf_counter() - 输入 loc_timestamp` 展示通信延迟。若客户端与服务端在不同机器，二者单调时钟基准不能默认直接相减；不过 loc_timestamp 原样回到同一客户端后再与该客户端时间相减，是另一种情况，不能混为一谈。

### 13.2 缓冲与等待速查

| 位置 | 当前策略 | 阅读时注意 |
| --- | --- | --- |
| 机器人进程图像池 | 每路默认 4 槽循环复用 | view 生命周期和覆盖 |
| RobotProxy 观测队列 | 默认容量 2，满时丢旧 | 主进程每次读取一项 |
| VLAClient 图像池 | 每路 30 槽 | 是第二层缓冲，不是同一池 |
| VLAClient 原始观测队列 | 容量 2，满时丢旧 | 注释与行为有不一致 |
| RDM 观测缓冲 | 默认最多 100，pop 取最新 | 更旧项仍可能留在缓冲 |
| 连续控制队列 | 未设 maxsize，消费端合并 | 不保证每条提交都执行 |
| 服务端发送队列 | 默认 1000，满时丢结果 | 返回入队成功不是送达确认 |
| 推理普通等待 | 默认 500 ms | 超时不取消服务端任务 |
| async 两轮间隔 | 默认 10 ms | 不是完整推理周期 |
| 手动 RPC | 默认 30 s 超时 | 与连续控制语义不同 |

### 13.3 最容易混淆的对应关系

| 容易误解 | 代码实际表示 |
| --- | --- |
| 模型发布动作就是发布电机命令 | 模型只返回目标块，客户端和 SDK 负责后续执行 |
| 30 FPS 模型需要每秒推理 30 次 | 一次推理可以返回很多未来动作点 |
| 3.75 ms 就是机器人伺服周期 | 这是上层回调配置，实际收包和低层周期另算 |
| action layout 列出头腰轮子就会全部被模型控制 | manual 维度默认排除在模型 action_dim 外 |
| RDM current_state 是实际关节反馈 | 此处是旧命令轨迹的状态 |
| gripper_offset=5 是提前 5 个训练帧 | 当前是拟合后的 5 列轨迹 |
| stepwise 夹爪值原样执行 | 会经过均值、阈值、移位、gamma 和分频 |
| shared memory 表示图像永远不会再变 | 槽循环复用，view 需要考虑持有时长 |
| history_frame 打开模型就会用历史 | 默认 GR00T 适配器只使用 sequence[0] |
| async 表示同一客户端无限并发模型请求 | 正常推理线程仍逐轮等待结果，只是与控制并行 |
| pause 后 resume 必然从全新计划开始 | 普通暂停未等价清空全部轨迹，需查看恢复路径 |
| 录制 action 就是实际 SDK 参数 | 录制点在 Proxy 提交后、RobotBody 变换前 |
| 任务进度达到阈值就证明物体已抓牢 | 这是模型进度机制，不是独立硬件成功回执 |

## 14 推荐的实际阅读方法

每一轮先打开表中的 2～3 个关键文件，只定位列出的函数，按本报告的调用顺序读。不要第一轮就试图逐行阅读两千行 Web 服务文件，也不要把所有模型适配器同时打开。

每轮给自己写四行笔记：**输入是什么、输出是什么、运行在哪个线程或进程、下一站是谁。** 涉及数组时补上形状和维度含义；涉及等待时补上超时、队列满和异常分支。读完本轮后，用该轮末尾的问题检查能否解释清楚，再进入下一轮。

重点文件可以用下面的只读命令快速列出函数位置：

```bash
cd /home/bjtc/Sophix/g1-open-rail
rg -n '^(class |def |    def |async def )' \
  client/core/vla_client.py \
  client/core/realtime_data_manager.py \
  client/robots/robot_proxy.py
```

本报告没有为阅读而启动任何入口。尤其 `run_web_client.py` 的启动会检查并终止占用指定 Web 端口的进程，完整 client start 又会开启控制；阅读入口源码与实际运行入口是两回事。

走完十轮后，应能从一份模型输出追到每个执行转换，再从一张头相机图像追到下一次模型输入，并能指出每一段的数据年龄、线程边界、动作变换和失败行为。需要进一步比较当前专用部署工程的设计时，可接着阅读 [g1 与 Open-RAIL 对比报告](/home/bjtc/Sophix/g1/文档/10-02-g1-open-rail与g1功能及执行流畅性对比报告.md)。

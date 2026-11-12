# 训练裁剪在部署端的接入建议

日期：2026-10-18

## 结论

建议在 Open-RAIL 的 LingBot 模型适配层增加可选图像预处理，位置是相机名映射完成后、`self.policy.infer(observation)` 之前。当前对应 server/models/lingbot_ori/lingbot_ori.py:ModelVLA.infer；NEWARTI 如使用同类裁剪权重，可复用同一预处理模块。裁剪参数随模型部署配置选择，不修改机器人驱动，也不全局修改 LingBot 的训练/推理核心。

## 1. crop_1016.py 实际做了什么（宽×高，坐标原点在左上）

| 相机 | 原训练视频尺寸 | ROI（x, y, w, h） | 脚本输出尺寸 |
| --- | --- | --- | --- |
| 头部 | 768×480 | (200, 0, 480, 480) | 224×224 |
| 左腕 | 848×480 | (184, 0, 480, 480) | 224×224 |
| 右腕 | 848×480 | 不裁剪，原样复制 | 848×480 |

右腕之后仍经过 LingBot 常规输入 resize，不能理解为最终模型输入保持 848×480。

对应数组切片为 `head[0:480,200:680]`、`left[0:480,184:664]`，右腕不裁剪。

脚本还变换 ECOT 的头部 bbox：`x'=(x-200)*224/480`，`y'=y*224/480`，并裁边界。state/action 不被裁剪脚本改变。

## 2. 必须补齐的头部尺寸转换

此前本机实测头部原图为 1280×800，左右腕为 848×480。

1015 转换代码 convert_datav2_1015.py 在生成头部视频时先以 Lanczos 缩放到 768×480；crop_1016.py 的 x=200 是这个坐标系中的值。

因此部署应先将头部图像缩放到 768×480，再执行上述 ROI 和 224×224 缩放。不能直接在 1280×800 上裁 x=200,w=480，也不能先把整图变为 224×224 再裁。

只接受明确支持的源尺寸；头部已经为 768×480 时不重复缩放，未知尺寸/宽高比应报错而不是猜测。

## 3. 为什么选择 Open-RAIL 模型适配层

当前链路：G1 图像 → Open-RAIL 客户端 JPEG 编码 → 服务端解码并转成 RGB → LingBot 适配器 → policy.infer → LingBot resize/归一化/FeatureTransform。

客户端 vision.preprocess 当前为 none，其通用函数不区分相机；全局改这里会影响网页预览和其他模型，也容易与服务端重复裁剪。

适配器已经知道 cam.head/hand_left/hand_right 的对应关系，适合按 checkpoint 决定视野。处理图像副本即可保留客户端原始图、现有记录和未裁剪模型的输入路径。

LingBot deploy/lingbot_vla_policy.py 的 resize_image 对各图执行 PIL BILINEAR → img_size（当前224）。只做这个 resize 不会复现训练裁剪；新增处理须位于它之前，常规归一化继续沿用原实现。

若以后还通过 LingBot 原生服务部署，应共享同一个裁剪函数/参数配置，并在原生入口接入，不能两边各写一套、同时重复生效。

## 4. 可选项建议

在模型服务端增加 image_profile：

| `image_profile` | 行为 |
| --- | --- |
| `original`（默认） | 保持现有未裁剪路径；不加 ROI 裁剪，原有模型 resize/归一化仍保留。 |
| `crop_1016` | 头部先恢复 768×480 坐标系，再按头部/左腕 ROI 裁剪并缩放到 224×224；右腕沿用原路径。 |

启动参数可设计为 `--image_profile original|crop_1016`，并打印所选配置及各路源尺寸/ROI/输出尺寸。建议与 checkpoint 部署配置绑定，在启动时选择；不要在 Control 运行中切换，以免旧动作队列与新图像配置混用。

可额外提供处理后画面预览用于对齐检查，但保留原始画面与原始数据记录。ECOT bbox 若需叠加回原图，必须使用逆坐标变换。

## 5. “相同输入”的验收与边界

从裁剪前视频取同一帧，分别运行训练参考转换与部署转换，对照头部/左腕 ROI、输出224×224、RGB顺序和右腕不裁剪；original 模式应不改变适配器输入像素。

核对实际模型的 resize/padding 配置，并防止客户端或公共服务端提前 resize。当前客户端 JPEG quality=80；训练脚本使用 FFmpeg 缩放、H.264 CRF18 和 yuv420p，再由训练加载器解码。仅使用 OpenCV/PIL 裁剪缩放不能承诺逐像素一致，应明确缩放算法、检查图像差异，优先保证视野/尺寸/颜色一致；不建议为了复刻压缩损失在在线推理中重复编码训练视频。

### 本机证据的限制

- datav2_1015_split 的当前元数据仍是头部768×480、左右腕848×480；cropped_data_1016 才声明头部/左腕224×224。

- crop_1016_repro/README.md 的示例输入为 marked_9_1_0922，而非1015。脚本支持传入其他数据目录，但单看脚本不能证明某次训练确实用了裁剪输出。

- 10-18-fulldata/step30000/lingbotvla_cli.yaml 记录远端 marked_9_1_0922/train 和 1015spilt/train、img_size=224，没有保存 ROI 参数。遵循用户说明按 crop_1016 设计部署方案，但上线前仍应对该次远端训练视频抽帧确认裁剪版本；不能仅凭目录名或 img_size=224 判断。

## 依据文件

- `/home/bjtc/Sophix/ORI-lingbot-vla/crop_1016.py`

- `/home/bjtc/Sophix/data_processing_conversion/convert_datav2_1015.py`

- `/home/bjtc/Sophix/ORI-lingbot-vla/deploy/lingbot_vla_policy.py`

- `/home/bjtc/Sophix/ORI-lingbot-vla/trained-model/10-18-fulldata/step30000/lingbotvla_cli.yaml`

- Open-RAIL：client/core/vla_client.py、server/core/vla_server.py、server/models/lingbot_ori/lingbot_ori.py、conf/lingbot_ori_package.yaml。

以上为最初的分析结论；后续实现状态见下节。

## 7. 实现状态（2026-10-18）

已在 Open-RAIL 的 ORI / NEWARTI 模型适配器中接入共享模块 `server/models/lingbot_image_profile.py`，在调用原生 policy 前处理图像副本。

- 默认 `original`，通过模型服务启动参数 `--image_profile crop_1016` 开启；恢复原路径用 `--image_profile original`。
- 头部支持 1280×800（先 Lanczos 到 768×480）及 768×480；左腕和右腕要求 848×480。头部和左腕按上述 ROI 裁剪，再用 Pillow Bicubic 到 224×224；右腕保持原像素。未知尺寸或已裁剪输入直接报错。
- 首次处理时记录每路源尺寸、ROI、输出尺寸。客户端显示与原始记录、state/action、Defaultpose 均不变。
- 已添加离线裁剪、输入保护、适配器传参及 CLI 配置测试。未启动真实模型或下发机器人动作；训练压缩与缩放造成的像素差异仍须按第 5 节验收。

启动示例见 [README-LingBot-G1.md](../README-LingBot-G1.md)。本次实现未自动选择 checkpoint，也未增加在线热切换或 bbox 原图叠加功能。

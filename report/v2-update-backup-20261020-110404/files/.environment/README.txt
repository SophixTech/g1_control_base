ORI-lingbot-vlaV2 uv 环境配置记录（2026-10-19）

使用：
  cd /home/bjtc/Sophix/ORI-lingbot-vlaV2
  source ./activate_uv.sh
  python .environment/verify.py
退出：deactivate
activate_uv.sh 会清除继承的 PYTHONPATH/PYTHONHOME，禁用用户 site-packages，
并将 uv 缓存指向 /home/bjtc/Sophix/.cache/uv；这些变量只影响当前 shell。

环境分析：
以 README.md、requirements.txt、requirements-depth.txt、tools/create_train_env.sh 为依据。
Python 3.12.3，PyTorch 2.8.0+cu128，torchvision 0.23.0+cu128，torchaudio 2.8.0+cu128，
torchcodec 0.6.0，torchdata 0.11.0，Transformers 4.57.3，tokenizers 0.22.2，
NumPy 1.26.4，LeRobot 0.4.2，numpydantic 1.9.0。
全部 requirements.txt 和 requirements-depth.txt 的锁定版本均匹配。
FlashAttention 复用现有 2.8.3.post1（官方脚本指定 2.8.3），CUDA 前向实测通过。
系统已有 CUDA Toolkit 12.8、FFmpeg 共享库；RTX 4090 24GB、驱动 595.71.05。
无需安装 Conda。

隔离与复用：
通过 uv venv 在本目录创建 .venv；复用同一只读基础 Python 解释器，第三方包不共用。
从 ../lingbot-vla/.venv 复制约 8.9GB 包，使用 cp --reflink=auto，不使用硬链接。
PyTorch、NVIDIA CUDA 库和 FlashAttention 未重新下载。
重写可执行脚本路径，移除旧 editable 绑定，将 lingbotvla/mdm/moge 重新安装至 V2 源码。
目标环境约 9.0GB；原环境未修改。
utils3d 复用已安装的官方指定 commit 3fab839f0be9931dac7c8488eb0e1600c236e183。
官方脚本引用的 morgbd_clean/3rd/utils3d 路径在本仓库不存在，因此没有创建该无效 .pth。
仅保留 headless OpenCV，避免两个 OpenCV wheel 覆盖同一个 cv2 目录。

安装策略及后续维护：
  uv pip install --python .venv/bin/python -r requirements.txt -r requirements-depth.txt \
    --override .environment/overrides.txt numpydantic==1.9.0 wheel
  uv pip install --python .venv/bin/python --no-deps --no-build-isolation \
    -e . -e lingbotvla/models/vla/vision_models/lingbot-depth \
    -e lingbotvla/models/vla/vision_models/MoGe
使用上述命令前先 source ./activate_uv.sh。
installed-requirements.txt 是本机版本快照，含本机 editable 路径；不是可直接 uv sync 的锁文件。

已知限制：
项目主依赖与子包声明不完全一致；dependency-check.txt 保存 19 项元数据冲突/缺失。
特别是 mlflow 要求 pyarrow<20，mlflow-skinny 要求 packaging<25，
numpydantic/plyfile 要求 NumPy>=2；这里保留仓库明确锁定的版本。
mdm 声明旧版 torch/xformers；LeRobot 声明另一些 torch/datasets 等版本，
按照项目训练环境策略不让子包改写主栈。没有安装 xformers、gradio、
LeRobot 的 pynput/rerun-sdk/cmake 等可选工具；headless OpenCV 提供 cv2，
但不满足名为 opencv-python 的包元数据。勿直接升级全部依赖或 uv sync。
这不是 uv pip check 全绿的通用 LeRobot/深度模型独立训练/演示环境。

验证：
verification.log：全部项目锁定版本、主要库导入、V2 训练入口导入均通过；
验证了源码路径属于 V2，RTX 4090 上 FlashAttention CUDA 前向计算通过。
可用 python .environment/verify.py 复查。验证需在可访问 GPU 的进程中运行。
未加载大模型权重或运行完整训练；模型权重、数据、归一化统计和训练配置路径
仍需按实际任务配置。单卡 24GB 是否足够取决于具体模型、训练策略和 batch size。

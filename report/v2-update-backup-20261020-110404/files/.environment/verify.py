"""Import and GPU smoke checks; does not load model weights or start training."""
import importlib
import importlib.metadata as md
from pathlib import Path
import runpy
import sys

root = Path(__file__).resolve().parents[1]
assert Path(sys.prefix) == root / '.venv'
assert not any('/Sophix/lingbot-vla/' in p for p in sys.path), sys.path
from packaging.requirements import Requirement
for filename in ('requirements.txt', 'requirements-depth.txt'):
    for line in (root / filename).read_text().splitlines():
        if not line.strip() or line.startswith('#'):
            continue
        req = Requirement(line)
        assert md.version(req.name) in req.specifier, (req, md.version(req.name))
print('All repository dependency pins match', flush=True)
for name in ('torch', 'torchvision', 'torchaudio', 'torchcodec', 'flash_attn',
             'transformers', 'lerobot', 'numpydantic', 'cv2', 'accelerate',
             'mlflow', 'oss2', 'moge.model.v2', 'mdm.model.v2', 'utils3d',
             'lingbotvla.utils.normalize'):
    module = importlib.import_module(name)
    print('IMPORT OK', name, getattr(module, '__file__', ''), flush=True)
for name in ('lingbotvla', 'moge', 'mdm'):
    module = importlib.import_module(name)
    paths = [module.__file__] if module.__file__ else list(module.__path__)
    assert all(Path(p).resolve().is_relative_to(root) for p in paths), paths
runpy.run_path(str(root / 'tasks/vla/train_lingbotvla.py'), run_name='environment_import_check')
print('Training entry import OK', flush=True)
import torch
print('Torch', torch.__version__, 'CUDA', torch.version.cuda, 'available', torch.cuda.is_available(), flush=True)
if torch.cuda.is_available():
    from flash_attn import flash_attn_func
    q = torch.randn(1, 16, 2, 64, device='cuda', dtype=torch.float16)
    out = flash_attn_func(q, q, q)
    torch.cuda.synchronize()
    assert out.shape == q.shape and torch.isfinite(out).all()
    print('FlashAttention CUDA forward OK:', torch.cuda.get_device_name(0), flush=True)
else:
    raise RuntimeError('GPU unavailable; rerun with GPU access')

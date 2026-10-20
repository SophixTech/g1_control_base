"""Independent full-finetuned NEWARTI LingBot adapter. Run in a fresh model-server process."""

import copy
import importlib
import json
import logging
from pathlib import Path
import struct
import sys

import numpy as np
import yaml

from server.models.lingbot_image_profile import ImageProfile


class ModelVLA:
    CAMERA_KEYS = {
        'cam.head': 'observation.images.cam_high_rgb',
        'cam.hand_left': 'observation.images.cam_left_wrist_rgb',
        'cam.hand_right': 'observation.images.cam_right_wrist_rgb',
    }
    MODULE = 'deploy.lingbot_vla_policy'
    MODEL_MODULE = 'lingbotvla.models.vla.pi0.modeling_lingbot_vla'

    @staticmethod
    def _check_import_origins(repo):
        # sys.path cannot fix an already imported package from another checkout.
        for name, module in list(sys.modules.items()):
            if not (name in ('deploy', 'lingbotvla') or name.startswith(('deploy.', 'lingbotvla.'))):
                continue
            origins = list(getattr(module, '__path__', []))
            if getattr(module, '__file__', None):
                origins.append(module.__file__)
            for origin in origins:
                if not Path(origin).resolve().is_relative_to(repo):
                    raise ImportError(f'NEWARTI import collision: {name} comes from {origin}; start a fresh process with {repo}')

    @classmethod
    def validate_artifacts(cls, config):
        """Read configs and safetensors headers only; no torch, CUDA or sockets."""
        for key in ('repo_path', 'model_path', 'norm_path'):
            if not config.get(key):
                raise ValueError(f'NEWARTI requires an explicit {key}')
        if type(config['chunk_size']) is not int or config['chunk_size'] != 50:
            raise ValueError('This NEWARTI adapter supports chunk_size=50 only')
        steps = config['num_denoising_step']
        if type(steps) is not int or steps <= 0:
            raise ValueError('num_denoising_step must be a positive integer')
        repo, checkpoint, norm = (Path(config[k]).expanduser().resolve()
                                  for k in ('repo_path', 'model_path', 'norm_path'))
        for module in (cls.MODULE, cls.MODEL_MODULE):
            path = repo.joinpath(*module.split('.')).with_suffix('.py')
            if not path.is_file():
                raise FileNotFoundError(path)
        training = yaml.safe_load((checkpoint / 'lingbotvla_cli.yaml').read_text())
        train, data = training['train'], training['data']
        if train.get('use_lora'):
            raise ValueError('NEWARTI requires full weights, not LoRA')
        if train.get('ecot_aux_supervision') is not True:
            raise ValueError('NEWARTI requires ecot_aux_supervision=true')
        if train.get('chunk_size') != 50 or data.get('data_name') != 'package_a2d':
            raise ValueError('NEWARTI checkpoint must use package_a2d and train.chunk_size=50')
        saved = json.loads((checkpoint / 'config.json').read_text())
        if saved.get('chunk_size') != 50 or saved.get('n_action_steps') != 50:
            raise ValueError('NEWARTI config.json must specify a 50-step horizon')
        # Training paths may belong to another machine; bind the native reset to this checkout.
        robot_file = repo / 'configs/robot_configs/package_a2d.yaml'
        layout = yaml.safe_load(robot_file.read_text())
        action_groups = {key: value for group in layout['actions'] for key, value in group.items()}
        arm = action_groups['action.arm.position']
        effector = action_groups['action.effector.position']
        if arm.get('subtract_state') is not True or effector.get('subtract_state', False):
            raise ValueError('NEWARTI expects delta arm actions and absolute gripper actions before unapply')
        stats = json.loads(norm.read_text())['norm_stats']
        for feature, shape in (('action.arm.position', (50, 14)),
                               ('action.effector.position', (2,)),
                               ('observation.state.arm.position', (14,)),
                               ('observation.state.effector.position', (2,))):
            for key in ('mean', 'std', 'min', 'max', 'q01', 'q99'):
                values = np.asarray(stats[feature][key], dtype=float)
                if values.shape != shape or not np.isfinite(values).all():
                    raise ValueError(f'Invalid NEWARTI normalization {feature}.{key}; expected finite {shape}')
        headers = {}
        shards = sorted(checkpoint.glob('*.safetensors'))
        if not shards:
            raise ValueError('NEWARTI checkpoint contains no safetensors weights')
        for shard in shards:
            with shard.open('rb') as stream:
                prefix = stream.read(8)
                if len(prefix) != 8:
                    raise ValueError(f'Incomplete safetensors file: {shard}')
                size = struct.unpack('<Q', prefix)[0]
                if size > 64 * 1024 * 1024 or size > shard.stat().st_size - 8:
                    raise ValueError(f'Invalid safetensors header length: {shard}')
                header = json.loads(stream.read(size))
            for key, value in header.items():
                if key == '__metadata__':
                    continue
                if key in headers:
                    raise ValueError(f'Duplicate checkpoint parameter: {key}')
                start, end = value['data_offsets']
                if not 0 <= start <= end <= shard.stat().st_size - 8 - size:
                    raise ValueError(f'Incomplete safetensors payload: {shard}: {key}')
                headers[key] = value
        if not headers:
            raise ValueError('NEWARTI checkpoint contains no parameters')
        if any('lora_' in key for key in headers):
            raise ValueError('NEWARTI requires full weights without LoRA parameters')
        flags = {}
        for key in ('ecot_aux_supervision', 'ecot_action_conditioning', 'ecot_visibility'):
            flags[key] = bool(train.get(key, False))
            if key in saved and saved[key] != flags[key]:
                raise ValueError(f'NEWARTI config.json and training disagree: {key}')
        heads = [('subtask', 4), ('bbox', 4), ('label', 2)]
        if flags['ecot_visibility']:
            heads.append(('visibility', 1))
        for head, outputs in heads:
            prefix = f'model.ecot_{head}_head'
            for layer in ('0.weight', '0.bias', '1.weight', '1.bias'):
                if f'{prefix}.{layer}' not in headers:
                    raise ValueError(f'Missing NEWARTI weight: {prefix}.{layer}')
            if headers[f'{prefix}.1.weight']['shape'][0] != outputs:
                raise ValueError(f'Wrong NEWARTI head shape: {prefix}')
        if flags['ecot_action_conditioning']:
            prefix = 'model.ecot_condition_proj.0'
            if any(f'{prefix}.{suffix}' not in headers for suffix in ('weight', 'bias')):
                raise ValueError('Missing NEWARTI action conditioning weights')
            if headers[f'{prefix}.weight']['shape'][1] != (11 if flags['ecot_visibility'] else 10):
                raise ValueError('Wrong NEWARTI conditioning input width')
        index_path = checkpoint / 'model.safetensors.index.json'
        if index_path.exists():
            weight_map = json.loads(index_path.read_text())['weight_map']
            if set(weight_map) != set(headers):
                raise ValueError('NEWARTI checkpoint shards do not match the weight index')
            for filename in set(weight_map.values()):
                if not (checkpoint / filename).is_file():
                    raise ValueError(f'Missing NEWARTI checkpoint shard: {filename}')
        return dict(model_type='lingbot_newarti', repo_path=str(repo), model_path=str(checkpoint),
                    norm_path=str(norm), robot_config=str(robot_file), chunk_size=50,
                    parameter_count=len(headers), ecot_flags=flags,
                    validation='metadata and weight headers only; model not instantiated')

    def __init__(self, config):
        self.cfg = config
        self.image_profile = ImageProfile(config.get("image_profile", "original"))
        self.chunk_size = 50
        artifacts = self.validate_artifacts(config)
        repo = Path(artifacts['repo_path'])
        self._check_import_origins(repo)
        sys.path.insert(0, str(repo))
        module = importlib.import_module(self.MODULE)
        self._check_import_origins(repo)
        model_module = importlib.import_module(self.MODEL_MODULE)
        if Path(module.__file__).resolve() != repo.joinpath(*self.MODULE.split('.')).with_suffix('.py'):
            raise ImportError('NEWARTI deployment entry was imported from the wrong checkout')
        if Path(model_module.__file__).resolve() != repo.joinpath(*self.MODEL_MODULE.split('.')).with_suffix('.py'):
            raise ImportError('NEWARTI model was imported from the wrong checkout')
        logging.getLogger(__name__).info('NEWARTI artifacts: %s; model source=%s', artifacts, model_module.__file__)
        # The upstream reset hardcodes a relative configs/ path. Bind only that
        # transform construction to our checkout, without changing process cwd.
        class NEWARTIPolicy(module.LingbotVLAServer):
            def reset(self, robo_name):
                if robo_name != 'package_a2d':
                    raise ValueError('NEWARTI adapter only supports package_a2d')
                self.global_step = 0
                self.last_action_chunk = None
                data_config = copy.copy(self.data_config)
                if getattr(data_config, 'joints', None) is not None:
                    # CLI exports may serialize these mappings as strings;
                    # hand-written YAML keeps dictionaries. Native expects strings.
                    data_config.joints = [repr(joint) if isinstance(joint, dict) else joint
                                          for joint in data_config.joints]
                self.vla.feature_transform = module.FeatureTransform(
                    artifacts['robot_config'], data_config,
                    self.language_tokenizer, self.processor.image_processor,
                    chunk_size=self.config.chunk_size, norm_stats_path=self.robot_norm_path,
                )

        # Native NEWARTI loader loads full weights with strict=True; no rtc_mode argument.
        self.policy = NEWARTIPolicy(
            path_to_pi_model=artifacts['model_path'], robot_norm_path=artifacts['norm_path'],
            use_length=50, num_denoising_step=config['num_denoising_step'],
            use_compile=False,
        )
        self.policy.reset('package_a2d')
        if self.policy.config.chunk_size != 50 or self.policy.vla.feature_transform.chunk_size != 50:
            raise ValueError('Loaded NEWARTI policy/FeatureTransform must have chunk_size=50')

    def infer(self, sequence):
        if len(sequence) != 1:
            raise ValueError('NEWARTI expects one observation without history frames')
        data = sequence[0]
        obs = data['obs']
        state = np.asarray(obs['state'])
        if state.shape not in ((16,), (20,)) or not np.isfinite(state[:16]).all():
            raise ValueError('NEWARTI state must be a finite 16- or 20-vector')
        language = obs['language']
        if isinstance(language, str) or len(language) != 1 or not isinstance(language[0], str):
            raise ValueError('NEWARTI language must contain one task string')
        observation = {'observation.state': np.array(state[:16], dtype=np.float32, copy=True),
                       'task': language[0]}
        for source, target in self.CAMERA_KEYS.items():
            frame = np.asarray(obs[source])
            if frame.ndim != 3 or frame.shape[2] != 3 or frame.dtype != np.uint8:
                raise ValueError(f'{source} must be HxWx3 RGB uint8')
            observation[target] = self.image_profile.apply(source, frame)
        response = self.policy.infer(observation)
        actions = np.array(response['action'], dtype=np.float32, copy=True)
        if actions.shape != (50, 16) or not np.isfinite(actions).all():
            raise ValueError('NEWARTI actions must be finite with shape (50, 16)')
        # Native FeatureTransform.unapply already restores absolute arm targets.
        return dict(type='vla_action', pred_action=actions,
                    ref_timestamp=data['ref_timestamp'], loc_timestamp=data['loc_timestamp'], ext={})

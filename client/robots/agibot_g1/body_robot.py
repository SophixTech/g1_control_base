import time
import cv2
import logging
import numpy as np
import pandas as pd
from concurrent.futures import ThreadPoolExecutor
from a2d_sdk.robot import RobotDds as Robot
from a2d_sdk.robot import CosineCamera as Camera
from ..base_robot import RobotBase
# from copy import copy


class RobotBody(RobotBase):
    def __init__(self, config):
        """Initialize the AgiBot G1 robot body with camera and robot instances.
        
        Args:
            config (dict): Configuration dictionary containing robot and camera settings
        """
        super().__init__(config)
        self.logger = logging.getLogger(__name__) # required for correct logging output
        self._cam_names = self.config['camera']['names']
        self._cam_ref = self.config['camera']['ref']
        self._cam_ref_name = self._cam_names[self._cam_ref]
        self._non_ref_cameras = [
            (key, value) for key, value in self._cam_names.items() if key != self._cam_ref
        ]
        workers_config = int(self.config['camera'].get('non_ref_fetch_workers', 2))
        self._non_ref_fetch_workers = workers_config if workers_config > 0 else 2
        self._non_ref_fetch_pool = None

        self.camera = Camera(list(self._cam_names.values()))
        self.robot = Robot()
        self._proprio_funs = [
            (proprio, getattr(self.robot, f'{proprio}_joint_states_nearest'))
            for proprio in self.config['proprio_names']
        ]

        self.current_state = np.zeros(self.action_dim, dtype=np.float32)
        self.current_timestamp = 0

        self._gripper_vmin = 35.0
        self._gripper_vmax = 120.0

        self.gripper_count = 0
        self._left_gripper_hold = None

        if self._non_ref_cameras and self._non_ref_fetch_workers > 0:
            self._non_ref_fetch_pool = ThreadPoolExecutor(
                max_workers=self._non_ref_fetch_workers,
                thread_name_prefix='agibot-g1-nonref-fetch'
            )

        time.sleep(1)

    @staticmethod
    def _check_fresh(stamp_ns, label):
        """Use the existing G1 deployment's 0.5-second feedback age limit."""
        if not stamp_ns:
            raise RuntimeError(f'{label} has no timestamp')
        age_s = abs((time.time_ns() - int(stamp_ns)) / 1e9)
        if age_s > 0.5:
            raise RuntimeError(f'{label} is stale ({age_s:.3f}s)')

    def _check_live_status(self):
        arm, arm_stamp = self.robot.arm_joint_states()
        self._check_fresh(arm_stamp, 'arm state')
        arm = np.asarray(arm, dtype=float)
        if arm.shape != (14,) or not np.isfinite(arm).all():
            raise RuntimeError('arm state must contain 14 finite values')
        status, status_stamp = self.robot.whole_body_status()
        self._check_fresh(status_stamp, 'whole_body_status')
        for key in ('left_arm_error', 'right_arm_error', 'left_end_error',
                    'right_end_error', 'waist_error', 'lift_error'):
            if int(status.get(key, 0)) != 0:
                raise RuntimeError(f'whole_body_status {key}={status[key]}')
        for key in ('left_arm_estop', 'right_arm_estop'):
            if bool(status.get(key, False)):
                raise RuntimeError(f'whole_body_status {key}=true')
        for key in ('left_arm_control', 'right_arm_control'):
            if not bool(status.get(key, False)):
                raise RuntimeError(f'whole_body_status {key}=false')

    def prepare_policy_control(self):
        """Sample the left gripper hold target without publishing any commands."""
        self._left_gripper_hold = None
        self._check_live_status()
        feedback, stamp = self.robot.gripper_states()
        self._check_fresh(stamp, 'gripper state')
        feedback = np.asarray(feedback, dtype=float)
        if feedback.shape != (2,) or not np.isfinite(feedback).all():
            raise RuntimeError('gripper state must contain 2 finite values')
        # Match G's raw/120 hold conversion; do not apply the right-gripper curve.
        self._left_gripper_hold = float(np.clip(feedback[0] / 120.0, 0.0, 1.0))
        self.gripper_count = 0

    def control_robot(self, action):
        """Execute a 16-D policy target: absolute arms, held left gripper, curved right."""
        action = np.asarray(action, dtype=float)
        if action.shape != (16,) or not np.isfinite(action).all():
            raise ValueError('G1 policy action must contain 16 finite values')
        if self._left_gripper_hold is None:
            raise RuntimeError('Call prepare_policy_control() before enabling G1 policy control')
        send_gripper = self.gripper_count % self.config['gripper_freq'] == 0
        self._check_live_status()
        self.robot.move_arm(action[:14].tolist())
        if send_gripper:
            right = float(np.clip(action[15], 0.0, 1.0))
            right = right ** 4 / (right ** 4 + (1.0 - right) ** 4)
            self.robot.move_gripper([self._left_gripper_hold, right])
            self.gripper_count = 0
        self.gripper_count += 1

    def execute_action(self, data):
        """Execute action interface without strategy.
        
        Args:
            data (dict): Dictionary containing arm and gripper commands
        """
        if 'arm' in data:
            self.robot.move_arm(data['arm'])
        if 'gripper' in data:
            self.robot.move_gripper(data['gripper'])
        if 'hand_as_gripper' in data:
            self.robot.move_hand_as_gripper(data['hand_as_gripper'])
        if 'head' in data:
            self.robot.move_head(data['head'])
        if 'waist' in data:
            self.robot.move_waist(data['waist'])
        if 'body' in data:
            self.robot.move_wbc_waist(data['body'])
        if 'wheel' in data:
            self.robot.move_wheel(data['wheel'][0], data['wheel'][1])
        if 'hand' in data:
            self.robot.move_hand(data['hand'])
    
    @staticmethod
    def _packet_to_bgr(packet):
        """Decode one packet to OpenCV BGR using that packet's own format metadata."""
        if packet is None:
            raise ValueError('Camera packet is unavailable')
        data = np.frombuffer(packet.get_image_data(), dtype=np.uint8)
        if str(packet.encoding_format).endswith(('JPEG', 'PNG')):
            image = cv2.imdecode(data, cv2.IMREAD_COLOR)
            if image is None:
                raise ValueError('Camera packet could not be decoded')
            return image
        color_format = str(packet.color_format)
        if color_format.endswith(('RGB', 'BGR')):
            image = data.reshape(packet.image_height, packet.image_width, 3)
            return cv2.cvtColor(image, cv2.COLOR_RGB2BGR) if color_format.endswith('RGB') else image.copy()
        raise ValueError(f'Unsupported camera color format: {color_format}')

    def _fetch_nearest_camera(self, camera_key, camera_name, ref_timestamp):
        packet = self.camera.get_packet_nearest(camera_name, ref_timestamp)
        return camera_key, self._packet_to_bgr(packet)

    def retrieve_observation(self):
        """Retrieve current observation data including camera images and joint states.

        Returns:
            dict or None: Dictionary containing camera images, joint states, and timestamp. Returns None if no new data is available.
        """
        try:
            result = {'ref_timestamp': None, 'obs.state': None}
            result[f'cam.{self._cam_ref}'] = None
            for key, _ in self._non_ref_cameras:
                result[f'cam.{key}'] = None

            packet = self.camera.get_latest_packet(self._cam_ref_name)
            if packet is None:
                return None
            ref_timestamp = packet.send_timestamp
            if self.current_timestamp == ref_timestamp:
                self.logger.debug("Retrieve image, return None.")
                time.sleep(0.01)
                return None

            # self.logger.debug(f'Retrieve image time: {(ref_timestamp - self.current_timestamp) / 1e6: .3f}ms')
            result['ref_timestamp'] = ref_timestamp
            result[f'cam.{self._cam_ref}'] = self._packet_to_bgr(packet)

            if self._non_ref_fetch_pool is not None:
                future_to_key = {
                    self._non_ref_fetch_pool.submit(self._fetch_nearest_camera, key, value, ref_timestamp): key
                    for key, value in self._non_ref_cameras
                }
                for future in future_to_key:
                    key, image = future.result()
                    result[f'cam.{key}'] = image

            state_size = 0
            state_parts = []
            gripper_start = None
            for proprio, joint_states_nearest_fun in self._proprio_funs:
                currt_joint_states, _ = joint_states_nearest_fun(ref_timestamp)
                curr_states = np.asarray(currt_joint_states, dtype=np.float32).ravel()

                if proprio == 'gripper':
                    gripper_start = state_size

                state_parts.append(curr_states)
                state_size += curr_states.size

            result['obs.state'] = np.concatenate(state_parts)
            if self.current_state.size < state_size:
                self.current_state = np.zeros(state_size, dtype=np.float32)

            self.current_state[:state_size] = result['obs.state']
            if gripper_start is not None and gripper_start + 2 <= state_size:
                gs = slice(gripper_start, gripper_start + 2)
                self.current_state[gs] -= self._gripper_vmin
                self.current_state[gs] /= (self._gripper_vmax - self._gripper_vmin)

            self.current_timestamp = ref_timestamp
            return result
        except Exception as e:
            self.logger.warning("retrieve_observation failed: %s", e, exc_info=True)
            return None

    def close(self):
        """Close and shutdown the robot and camera connections.
        
        This method properly releases all hardware resources.
        """
        if self._non_ref_fetch_pool is not None:
            self._non_ref_fetch_pool.shutdown(wait=True)
            self._non_ref_fetch_pool = None

        self.camera.close()
        self.robot.shutdown()
        print('close robot')

    def load_action_data(self, parquet_path, key="action"):
        """ read specific data from parquet file

        Args:
            parquet_path: the parquet file path 
            key: key of data, for example, action, observation.state
        """
        # read parquet file
        df = pd.read_parquet(parquet_path)
        data = df[key].tolist()
        # process data of dexterous hand to gripper format
        processed_data = []
        for idx, ele in enumerate(data):
            if 'hand' in self.config['hand_type']:
                data_temp = np.zeros(20)
                data_temp[:14] = ele[:14]
                left_hand = ele[15:19].mean()
                if left_hand > 0.1:
                    left_hand = 1.0
                right_hand = ele[20:23].mean()
                if right_hand < 0.1:
                    right_hand = 0
                data_temp[14] = left_hand
                data_temp[15] = right_hand
                processed_data.append(data_temp)
            else:
                processed_data.append(ele)
        return processed_data

    def default_replay_trajectories(self, parquet_path, accelerate:bool=True, accelerate_times: int=2):
        trajs = self.load_action_data(parquet_path=parquet_path)
        if not accelerate:
            accelerate_times = 1
        for idx, traj in enumerate(trajs):
            if idx % accelerate_times == 0:
                self.execute_action({'arm': traj[0:14].tolist()})
                self.execute_action({self.config['hand_type']: traj[14:16].tolist()})
                time.sleep(0.05)

    def replay_trajectories(self, parquet_path, use_default: bool=True, accelerate:bool=True, accelerate_times: int=2, exclude_path=['place'], progress_fn=None):
        """replay trajectory based on teleoperation data"""
        try:
            if 'hand' in self.config['hand_type']:
                use_default = False

            if use_default:
                self.default_replay_trajectories(parquet_path=parquet_path, accelerate=accelerate, accelerate_times=accelerate_times)
            else:
                trajs = self.load_action_data(parquet_path=parquet_path)
                for ele in exclude_path:
                    if ele in parquet_path:
                        accelerate = False
                for idx, traj in enumerate(trajs):
                    if progress_fn is not None:
                        progress_fn(idx, len(trajs), traj)

                    if accelerate:
                        if idx % accelerate_times == 0:
                            self.execute_action({'arm': traj[0:14].tolist()})
                            if 'place_fruit' in parquet_path and idx < len(trajs)-30 and idx > 200:
                                traj[14] = 1.0
                                traj[15] = 0.0
                            self.execute_action({self.config['hand_type']: traj[14:16].tolist()})
                            time.sleep(0.05)
                    else:
                        self.execute_action({'arm': traj[0:14].tolist()})
                        if 'place_fruit' in parquet_path and idx < len(trajs)-30 and idx > 200:
                            traj[14] = 1.0
                            traj[15] = 0.0
                        self.execute_action({self.config['hand_type']: traj[14:16].tolist()})
                        time.sleep(0.05)
        except Exception as e:
            print(f"Replay {parquet_path} failed, error: {e}")

if __name__ == '__main__':
    from conf.robots_conf import get_robots_config
    config = get_robots_config()
    robot = RobotBody(config)
    try:
        while True:
            result = robot.retrieve_observation()
            if result is None:
                continue
            for key, value in result.items():
                if 'cam.' not in key:
                    continue
                if 'depth.' in key:
                    img_depth_norm = cv2.normalize(value, None, 0, 255, cv2.NORM_MINMAX, dtype=cv2.CV_8U)
                    img_show = cv2.applyColorMap(img_depth_norm, cv2.COLORMAP_JET)
                else:
                    img_show = cv2.cvtColor(value, cv2.COLOR_RGB2BGR)
                cv2.imshow(key, img_show)
                cv2.waitKey(1)
    except KeyboardInterrupt:
        robot.close()

"""GDK 1.5 BodyPose unit compatibility for the G1 deployment."""
import math

from a2d_sdk.robot import RobotDds
from genie_msgs_pb.srv.BodyPose_pb2 import BodyPose_Request


class Robot(RobotDds):
    def move_head(self, positions, uint_radian=False):
        # The SDK cache mixes head degrees, waist radians and lift metres.
        # BodyPose expects degrees and centimetres for ALL entries, including
        # the waist entries attached to a head-only request (joint_flag=3).
        values = list(self._body_pose_joint_states)
        values[0] = math.degrees(positions[0])
        values[1] = math.degrees(positions[1])
        values[2] = math.degrees(values[2])
        values[3] *= 100.0
        request = BodyPose_Request()
        request.joint_states.extend(values)
        request.joint_flag = 3
        return self._body_pose_client.send_request(request)

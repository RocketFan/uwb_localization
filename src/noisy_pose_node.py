import rospy
import random
import numpy as np

from abc import ABC, abstractmethod
from geometry_msgs.msg import Pose, PoseStamped, PoseWithCovarianceStamped
from gazebo_msgs.msg import ModelStates
from nav_msgs.msg import Path


class PoseNoise(ABC):
    def __init__(self):
        pass

    def init(self):
        self.cov_matrix = self.calc_cov_matrix()

    def applay(self, pose: Pose):
        position = pose.position
        position.x += self.get_noise()
        position.y += self.get_noise()
        position.z += self.get_noise()

    def calc_cov_matrix(self) -> np.array:
        example_poses = [[self.get_noise(),
                          self.get_noise(),
                          self.get_noise(),
                          0, 0, 0] for _ in range(100)]
        example_poses_np = np.array(example_poses).T
        cov_matrix = np.cov(example_poses_np).astype(float)

        return cov_matrix

    def get_cov_matrix(self):
        return self.cov_matrix

    @abstractmethod
    def get_noise(self) -> int:
        pass


class PoseRandomNoise(PoseNoise):
    def __init__(self, offset):
        super().__init__()
        self.offset = offset
        self.init()

    def get_noise(self) -> int:
        return (random.random() * self.offset) - self.offset / 2


def extract_id(name: str):
    id = name.replace('uav', '')
    return int(id)


class UAVPublisher:
    def __init__(self, name, pose_noise: PoseNoise):
        self.pose_noise = pose_noise
        self.id = extract_id(name)
        self.name = name

        self.path_msg = Path()
        self.path_msg.header.frame_id = 'map'
        self.path_timer = rospy.Timer(rospy.Duration(0.1), lambda _: self.update_path_msg())
        self.path_max = 400

        self.noisy_pose_msg = None
        self.noisy_pose_pub = rospy.Publisher(f'/{self.name}/noisy/pose_cov', PoseWithCovarianceStamped, queue_size=10)
        self.path_pub = rospy.Publisher(f'/{self.name}/noisy/path', Path, queue_size=10)

    def publish(self):
        if self.noisy_pose_msg:
            msg = self.get_pose_with_covariance()
            self.noisy_pose_pub.publish(msg)

        self.path_pub.publish(self.path_msg)

    def update_noisy_pose_msg(self, noisy_pose_msg):
        self.noisy_pose_msg = noisy_pose_msg

    def update_path_msg(self):
        if self.noisy_pose_msg:
            self.path_msg.poses.append(self.get_pose_stamped())
            
            if len(self.path_msg.poses) > self.path_max:
                self.path_msg.poses.pop(0)

    def get_pose(self):
        index = self.noisy_pose_msg.name.index(self.name)
        msg = self.noisy_pose_msg.pose[index]

        return msg

    def get_pose_stamped(self):
        msg = PoseStamped()
        msg.header.frame_id = 'map'
        msg.pose = self.get_pose()
        
        return msg

    def get_pose_with_covariance(self):
        msg = PoseWithCovarianceStamped()
        msg.header.frame_id = 'map'
        msg.pose.pose = self.get_pose()
        msg.pose.covariance = self.pose_noise.get_cov_matrix().flatten().tolist()

        return msg

class NoisyPositionNode:
    def __init__(self):
        self.noise = PoseRandomNoise(1)
        self.uav_names = []
        self.uavs = []
        self.rate = rospy.Rate(30)

        self.sub_states = rospy.Subscriber(
            "/ground_truth", ModelStates, self.states_callback)
        self.pub_noisy_position = rospy.Publisher(
            "/noisy_position", ModelStates, queue_size=1)

    def run(self):
        while not rospy.is_shutdown():
            for uav in self.uavs:
                uav.publish()
            self.rate.sleep()

    def states_callback(self, data: ModelStates):
        poses = data.pose

        for pose in poses:
            self.noise.applay(pose)

        new_uav_names = self.update_uav_names(data.name)
        self.add_uavs(new_uav_names)
        self.update_uavs(data)
        self.publish_noisy_position(data)

    def update_uav_names(self, names):
        new_uav_names = []

        for name in names:
            if name not in self.uav_names:
                new_uav_names.append(name)
                self.uav_names.append(name)

        return new_uav_names

    def add_uavs(self, names):
        for name in names:
            self.uavs.append(UAVPublisher(name, self.noise))

    def update_uavs(self, noisy_pose_msg):
        for uav in self.uavs:
            uav.update_noisy_pose_msg(noisy_pose_msg)

    def publish_noisy_position(self, data: ModelStates):
        msg = ModelStates()
        msg.name = data.name
        msg.pose = data.pose
        self.pub_noisy_position.publish(msg)


if __name__ == '__main__':
    try:
        rospy.init_node('noisy_pose_node', anonymous=True)
        node = NoisyPositionNode()
        node.run()
    except rospy.ROSInterruptException:
        pass

#!/usr/bin/env python
import rospy
import numpy as np

from geometry_msgs.msg import PoseStamped
from gazebo_msgs.msg import ModelStates

def extract_id(name: str):
    id = name.replace('uav', '')
    return int(id)

class UAVPublisher:
    def __init__(self, name):
        self.id = extract_id(name)
        self.name = name
        self.ground_truth_msg = None
        self.ground_truth_pub = rospy.Publisher(f'/{self.name}/ground_truth', PoseStamped, queue_size=10)

    def publish(self):
        if self.ground_truth_msg:
            msg = self.get_ground_truth_pose()
            self.ground_truth_pub.publish(msg)

    def update_ground_truth_msg(self, ground_truth_msg):
        self.ground_truth_msg = ground_truth_msg

    def get_ground_truth_pose(self):
        msg = PoseStamped()
        msg.header.frame_id = 'map'
        index = self.ground_truth_msg.name.index(self.name)
        msg.pose = self.ground_truth_msg.pose[index]

        return msg
            

class GroundTruthNode:
    def __init__(self):
        self.uav_names = []
        self.uavs = []
        self.rate = rospy.Rate(30)

        self.uav_name_prefix = rospy.get_param('~uav_name_prefix')
        self.sub_states = rospy.Subscriber(
            "/gazebo/model_states", ModelStates, self.states_callback)
        self.pub_ground_truth = rospy.Publisher(
            "/ground_truth", ModelStates, queue_size=1)

    def run(self):
        while not rospy.is_shutdown():
            for uav in self.uavs:
                uav.publish()
            self.rate.sleep()

    def states_callback(self, data: ModelStates):
        ground_truth_compressed = self.create_ground_truth_compressed(data)
        msg = self.create_ground_truth_msg(ground_truth_compressed)
        new_uav_names = self.update_uav_names(msg.name)
        self.add_uavs(new_uav_names)
        self.update_uavs(msg)
        self.pub_ground_truth.publish(msg)

    def create_ground_truth_compressed(self, data: ModelStates):
        names = data.name
        poses = data.pose
        ground_truth_compressed = [[n.replace(self.uav_name_prefix, 'uav'), p] for n, p in zip(
            names, poses) if n.startswith(self.uav_name_prefix)]

        return ground_truth_compressed

    def update_uav_names(self, names):
        new_uav_names = []

        for name in names:
            if name not in self.uav_names:
                new_uav_names.append(name)
                self.uav_names.append(name)

        return new_uav_names
    
    def add_uavs(self, names):
        for name in names:
            self.uavs.append(UAVPublisher(name))

    def update_uavs(self, ground_truth_msg):
        for uav in self.uavs:
            uav.update_ground_truth_msg(ground_truth_msg)

    def create_ground_truth_msg(self, ground_truth_array):
        msg = ModelStates()
        ground_truth_array = np.array(sorted(ground_truth_array, key=lambda x: x[0]))
        msg.name = list(ground_truth_array[:, 0])
        msg.pose = list(ground_truth_array[:, 1])

        return msg


if __name__ == '__main__':
    try:
        rospy.init_node('ground_truth_node', anonymous=True)
        node = GroundTruthNode()
        node.run()
    except rospy.ROSInterruptException:
        pass
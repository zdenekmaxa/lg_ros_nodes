#!/usr/bin/env python

import os
import rospy
import subprocess
from std_msgs.msg import Byte
from lg_common.helpers import run_with_influx_exception_handler


DEVNULL = open(os.devnull, 'w')
CLEAR_BUTTON = 2
NODE_NAME = 'rfreceiver_kill_browser'


class RfreceiverAction:
    def __init__(self):
        rospy.init_node(NODE_NAME)
        self.clear_button_message = rospy.get_param('~clear_button_message', 2)
        self.fallback_mode = rospy.get_param('~fallback_mode', 'tactile')
        self.reset_command = rospy.get_param('~reset_command', 'pkill chrome')

    def handle_button_msg(self, msg):
        if msg.data == self.clear_button_message:
            subprocess.call(
                ['/home/lg/bin/lg-run-bg', self.reset_command],
                stdout=DEVNULL,
                stderr=DEVNULL
            )

    def main(self):
        buttondown_pub = rospy.Subscriber(
            '/rfreceiver/buttondown',
            Byte,
            self.handle_button_msg
        )

        rospy.spin()

if __name__ == '__main__':
    run_with_influx_exception_handler(RfreceiverAction().main, NODE_NAME)

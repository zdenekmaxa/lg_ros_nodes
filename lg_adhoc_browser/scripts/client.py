#!/usr/bin/env python
"""
TODO: Browser is not changing url yet.
"""

import rospy
from lg_adhoc_browser.msg import AdhocBrowsers
from lg_adhoc_browser import Client


def main():
    rospy.init_node('lg_adhoc_browser')

    vieport_name = rospy.get_param('~viewport', None)

    if not vieport_name:
        rospy.logerr("Viewport is not set in the roslaunch file. Exiting.")
        exit(1)

    topic_name = '/browser_service/{}'.format(vieport_name)
    client = Client()

    rospy.Subscriber(topic_name, AdhocBrowsers, client.handle_ros_message) 

    rospy.spin()


if __name__ == "__main__":
    main()
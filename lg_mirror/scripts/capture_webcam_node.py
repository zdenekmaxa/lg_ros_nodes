#!/usr/bin/env python

import rospy
from lg_mirror.capture_webcam import CaptureWebcam
from lg_common.helpers import run_with_influx_exception_handler

NODE_NAME = 'mirror_capture_webcam'


def required_param(key, coer=None):
    val = rospy.get_param(key)
    if val is None:
        raise ValueError('"{}" param required'.format(key))
    if coer is not None:
        val = coer(val)
    return val


def main():
    rospy.init_node(NODE_NAME)

    janus_host = required_param('/lg_mirror/janus_stream_host', str)
    janus_port = required_param('~janus_port', int)
    device = rospy.get_param('~device', '/dev/capture_cam')
    width = int(rospy.get_param('~width'))
    height = int(rospy.get_param('~height'))
    framerate = int(rospy.get_param('~framerate'))
    max_quantizer = int(rospy.get_param('~max_quantizer', 60))
    target_bitrate = int(rospy.get_param('~target_bitrate', 768000))

    capture = CaptureWebcam(
        janus_host,
        janus_port,
        device,
        width,
        height,
        framerate,
        max_quantizer,
        target_bitrate,
    )

    capture.start_capture()

    rospy.spin()


if __name__ == '__main__':
    run_with_influx_exception_handler(main, NODE_NAME)

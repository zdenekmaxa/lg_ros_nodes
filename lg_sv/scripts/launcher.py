#! /usr/bin/env python

import rospy

from lg_common import ManagedWindow, ManagedBrowser
from lg_common.msg import ApplicationState
from lg_common.helpers import add_url_params

DEFAULT_URL = 'http://localhost:8008/lg_sv/webapps/client/index.html'


def main():
    rospy.init_node('streetview_browser', anonymous=True)
    geometry = ManagedWindow.get_viewport_geometry()
    url = str(rospy.get_param('~url', DEFAULT_URL))
    yaw_offset = float(rospy.get_param('~yaw_offset', 0))
    pitch_offset = float(rospy.get_param('~pitch_offset', 0))
    show_links = str(rospy.get_param('~show_links', False)).lower()
    # put parameters into one big url
    url = add_url_params(url, yawOffset=yaw_offset, pitchOffset=pitch_offset, showLinks=show_links)
    # create the managed browser
    managed_browser = ManagedBrowser(url=url, geometry=geometry)

    # set to visible
    state = ApplicationState.VISIBLE
    managed_browser.set_state(state)

    # listen to state messages
    rospy.Subscriber('/streetview/state', ApplicationState, managed_browser.handle_state_msg)

    rospy.spin()

if __name__ == '__main__':
    main()
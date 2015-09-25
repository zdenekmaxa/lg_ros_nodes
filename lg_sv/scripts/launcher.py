#! /usr/bin/env python

import rospy

from lg_common import ManagedWindow, ManagedBrowser, ManagedAdhocBrowser
from lg_common.msg import ApplicationState
from lg_common.helpers import add_url_params
from lg_common.helpers import dependency_available
from lg_common.helpers import discover_port_from_url, discover_host_from_url
from lg_common.helpers import DependencyException

DEFAULT_URL = 'http://localhost:8008/lg_sv/webapps/client/index.html'
#FOV for zoom level 3
DEFAULT_FOV = 28.125


def main():
    rospy.init_node('panoviewer_browser', anonymous=True)

    geometry = ManagedWindow.get_viewport_geometry()
    server_type = rospy.get_param('~server_type', 'streetview')
    url = str(rospy.get_param('~url', DEFAULT_URL))
    field_of_view = float(rospy.get_param('~fov', DEFAULT_FOV))
    pitch_offset = float(rospy.get_param('~pitch_offset', 0))
    show_links = str(rospy.get_param('~show_links', False)).lower()
    yaw_offset = float(rospy.get_param('~yaw_offset', 0))
    leader = str(rospy.get_param('~leader', 'false'))
    tilt = str(rospy.get_param('~tilt', 'false'))
    depend_on_webserver = rospy.get_param('~depend_on_webserver', False)

    # put parameters into one big url
    url = add_url_params(url,
                         fov=field_of_view,
                         pitchOffset=pitch_offset,
                         showLinks=show_links,
                         leader=leader,
                         yawOffset=yaw_offset,
                         tilt=tilt)

    # check if server is already there
    host = discover_host_from_url(url)
    port = discover_port_from_url(url)
    timeout = rospy.get_param('/global_dependency_timeout', 15)

    if not depependecy_available(host, port, 'streetview_server', timeout) and depend_on_webserver:
        msg = "Streetview server (%s:%s) did not appear within specified timeout of %s seconds" % (host, port, timeout)
        rospy.logerr(msg)
        raise DependencyException
    else:
        rospy.loginfo("Launching client browser without waiting for webserver")

    # create the managed browser
    slug = server_type + str(field_of_view) + str(yaw_offset) + str(pitch_offset)
    managed_browser = ManagedAdhocBrowser(url=url, geometry=geometry, slug=slug)

    # set to visible
    state = ApplicationState.HIDDEN
    managed_browser.set_state(state)

    # listen to state messages
    rospy.Subscriber('/%s/state' % server_type, ApplicationState, managed_browser.handle_state_msg)

    rospy.spin()

if __name__ == '__main__':
    main()

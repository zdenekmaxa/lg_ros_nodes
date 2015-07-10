#!/usr/bin/env python
import rospy
from lg_earth import KmlSyncState
from interactivespaces_msgs.msg import GenericMessage
from lg_earth.srv import KmlState, PlaytourQuery

def main():
    rospy.init_node('kml_service', anonymous=True)

    topic = rospy.get_param('~director_topic', '/director/scene')
    service_channel = rospy.get_param('~service_channel', 'kmlsync/state')
    playtour_channel = rospy.get_param('~playtour_channel', 'kmlsync/playtour_query')
    s = KmlSyncState()
    rospy.Subscriber(topic, GenericMessage, s._save_state)
    rospy.Service(service_channel, KmlState, s._process_service_request)
    rospy.Service(playtour_channel, PlaytourQuery, s._send_playtour_query)

    rospy.spin()

if __name__ == '__main__':
    main()
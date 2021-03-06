#!/usr/bin/env python

import rospy
import sys
import threading
import json

from lg_common.helpers import unpack_activity_sources
from lg_common.helpers import list_of_dicts_is_homogenous
from lg_common.helpers import rewrite_message_to_dict
from lg_common.helpers import get_message_type_from_string
from lg_common.helpers import get_nested_slot_value
from std_msgs.msg import Bool


class ActivitySourceNotFound(Exception):
    pass


class ActivitySourceException(Exception):
    pass


class ActivityTrackerException(Exception):
    pass


class ActivitySource:
    """
    Should be instantiated with topic, message_type and strategy

    Provides:
    - subscription to topic of activity (e.g touchscreen or spacenav)
    - storage for all messages flowing on a given topic with some memory limit
    - checking for a slot if strategy is based on single attribute lookup. The slot can be nested like: angular.x
      in geometry_msgs/Twist case this will check for Twist().angular 'x' attribute
    - minimum/maximum value for 'value' strategy - everything outside of the constraints **is** activity
      for `value` kind of strategy, a slot is needed
    - memory limit for messages storage - by default 1024000 (1MB)
        e.g. 10k geometry_msg/Twist messages = 87632 bytes
    - "is_active" method that should
     - return True/False if aggregated list of events (from the specified topic)
     triggered the activity by applying the provided strategy type
     - erase aggregated messages upon "is_active" call
    """
    DELTA_MSG_COUNT = 15

    def __init__(self, memory_limit=1024000,
                 topic=None, message_type=None,
                 strategy=None, slot=None,
                 value_min=None, debug=None,
                 value_max=None, callback=None):
        self._check_init_args(topic, message_type, strategy, callback,
                              value_min, value_max, slot)
        self.message_type = message_type
        self.callback = callback
        self.slot = slot
        self.strategy = strategy
        self.value_min = value_min
        self.value_max = value_max
        self.debug = debug
        self.topic = topic
        self.memory_limit = memory_limit
        self.messages = []
        self.delta_msg_count = self.__class__.DELTA_MSG_COUNT

        self._initialize_subscriber()
        rospy.loginfo("Initialized ActivitySource: %s" % self)

    def _check_init_args(self, topic, message_type, strategy, callback, value_min, value_max, slot):
        """
        ActivitySource is v fragile when it comes to initialization and subscriptions
        This method provides all sanity checks for that
        """
        if (not topic) or (not message_type) or (not strategy) or (not callback):
            msg = "Could not initialize ActivitySource: topic=%s, message_type=%s, strategy=%s, callback=%s" % \
                (topic, message_type, strategy, callback)
            rospy.logerr(msg)
            raise ActivitySourceException(msg)

        if (type(topic) != str) or (type(message_type) != str):
            msg = "Topic and message type should be strings"
            rospy.logerr(msg)
            raise ActivitySourceException(msg)

        if strategy == 'value':
            """
            For 'value' strategy we need to provide a lot of data
            """
            if value_min and value_max and slot:
                rospy.loginfo("Registering activity source with min=%s, max=%s and msg attribute=%s" %
                              (value_min, value_max, slot))
            else:
                msg = "Could not initialize 'value' stragegy for ActivitySource. All attrs are needed (min=%s, max=%s and msg attribute=%s)" % \
                    (value_min, value_max, slot)
                rospy.logerr(msg)
                raise ActivitySourceException(msg)

    def __str__(self):
        """
        String representation of the ActivitySource - needed by pretty logs
        """
        string_representation = "<ActivitySource: slot: %s, strategy: %s, value_min:%s, value_max:%s on topic %s>" % \
            (self.slot, self.strategy, self.value_min, self.value_max, self.topic)
        return string_representation

    def __repr__(self):
        """
        __repr__ representation of the ActivitySource - needed by pretty logs
        """
        string_representation = "<ActivitySource: slot: %s, strategy: %s, value_min:%s, value_max:%s on topic %s>" % \
            (self.slot, self.strategy, self.value_min, self.value_max, self.topic)
        return string_representation

    def _initialize_subscriber(self):
        """
        Performes a dirty python stuff to subscribe to a topic using
        message type provided with a string in '<module>/<msg>' format
        """
        try:
            message_type_final = get_message_type_from_string(self.message_type)
        except Exception, e:
            msg = "Could not import module because: %s" % (e)
            rospy.logerr(msg)
            raise ActivitySourceException

        rospy.loginfo("ActivitySource is going to subscribe topic: %s with message_type: %s" % (self.topic, message_type_final))
        self.subscriber = rospy.Subscriber(self.topic, message_type_final, self._aggregate_message)

    def _aggregate_message(self, message):
        """
        Check for memory limits, deserialize message to python dict, append message to
        ActivitySource buffer for later calculations
        """
        while sys.getsizeof(self.messages) >= self.memory_limit:
            rospy.logwarn("%s activity source memory limit reached (%s) - discarding oldest message" % (self.topic, self.memory_limit))
            if len(self.messages) <= 1:
                rospy.logwarn("Too small of a memory limit set... Ignoring")
                break
            del self.messages[0]

        self._deserialize_and_append(message)
        self.is_active()

    def _get_slot_value_from_message(self, message):
        """
        For every strategy, if 'slot' is specified, it can be nested e.g.:
            linear:
                x: 0.0
                y: 0.0
                z: 0.0
            angular:
                x: 0.0
                y: 0.0
                z: 0.0

        User can specify slot like 'linear.x' and this method is responsible for retrieving it
        and returning as a dictionary e.g. {'linear.x': 'some_value'}
        """

        return get_nested_slot_value(self.slot, message)

    def _deserialize_and_append(self, message):
        """
        Takes all message slots and turns the message into a dict.
        If single slot was provided than we're using only the provided one
        """

        deserialized_msg = {}

        if self.slot:
            deserialized_msg = self._get_slot_value_from_message(message)
        else:
            deserialized_msg = rewrite_message_to_dict(message)

        self.messages.append(deserialized_msg)

    def _messages_met_value_constraints(self):
        """
        Checks accumulated messages (typically 1 message)
        And finds out if value of the slot (e.g. 3.17)
        is within value_min:value_max range. If it's within
        the range, then method returns False meaning that
        values exceeded the range (making system active)

        Values outside of the value_min/value_max range make
        system become inactive.
        """
        for message in self.messages:
            value = float(message.values()[0])
            if value >= float(self.value_min) and value <= float(self.value_max):
                return False
        return True

    def is_active(self):
        """
        Apply strategy to self.messages:
            - delta - compares messages
            - value - checks for specific value
            - activity - checks for any messages flowing on a topic

        Once state is asserted then call ActivityTracker to let him know
        what's the state of the source

        This method can be called from 'self' as well as from the outside of self
        """
        if self.strategy == 'delta':
            self._is_delta_active()
        elif self.strategy == 'value':
            self._is_value_active()
        elif self.strategy == 'activity':
            self._is_activity_active()
        else:
            rospy.logerr("Unknown strategy: %s for activity on topic %s" % (self.strategy, self.topic))

    def _is_delta_active(self):
        """
        Checks whether all messages (of type dict) stored in the buffer are
        homogenous. If they are not then this activity source is active
        """
        if len(self.messages) < self.delta_msg_count:
            rospy.logdebug("Not enough messages (minimum of %s) for 'delta' strategy" % self.delta_msg_count)
            return

        if list_of_dicts_is_homogenous(self.messages):
            self.messages = self.messages[-self.delta_msg_count + 1:]
            self.callback(self.topic, state=False, strategy='delta')
            return False  # if list if homogenous than there was no activity
        else:
            self.messages = self.messages[-self.delta_msg_count + 1:]
            self.callback(self.topic, state=True, strategy='delta')
            return True  # if list is not homogenous than there was activity

    def _is_value_active(self):
        """
        If current message meets value constrains then the system is active
        """
        if self._messages_met_value_constraints():
            self.callback(self.topic, state=False, strategy='value')
            self.messages = []
            return False  # messages met the constraints
        else:
            self.callback(self.topic, state=True, strategy='value')
            self.messages = []
            return True  # messages didnt meet the constraints

    def _is_activity_active(self):
        """
        Here's the place where ActivitySource triggers ActivityTracker, which is its parent
        to inform it that it's active
        """
        if len(self.messages) > 0:
            self.messages = []
            self.callback(self.topic, state=True, strategy='activity')
            return True
        else:
            self.callback(self.topic, state=False, strategy='activity')
            return False


class ActivitySourceDetector:
    """
    Provides a getter for a dictionary of topics, messages and strategies e.g.:
    example source:

    source = { "topic": "/touchscreen/touch",
               "message_type": "interactivespaces_msgs/String",
               "strategy": "activity",
               "slot": None,
               "value_min": None,
               "value_max": None
             }
    """
    def __init__(self, sources_string):
        self.sources = unpack_activity_sources(sources_string)
        rospy.loginfo("Initialized ActivitySourceDetector: %s" % self)

    def __str__(self):
        string_representation = "<ActivitySourceDetector: sources: %s" % self.sources
        return string_representation

    def __repr__(self):
        string_representation = "<ActivitySourceDetector: sources: %s" % self.sources
        return string_representation

    def get_sources(self):
        return self.sources

    def get_source(self, topic):
        """
        Returns single source by topic name
        """
        try:
            source = [source for source in self.sources if source['topic'] == topic]
            return source[0]
        except KeyError, e:
            msg = "Could not find source %s because %s" % (source, e)
            rospy.logerr(msg)
            raise ActivitySourceNotFound(msg)


class ActivityTracker:
    """
    Provides callback that should be passed to ActivitySources.

    Each ActivitySource will call the callback upon the activity
    coming on a topic that the ActivitySource is watching.

    Provides a topic /activity/active and emits a active: True|False message
    depending on the activity state change

    Keeps the state of activity. State should be 'active: true' by default

    Provides service for checking the activity state

    """

    def __init__(self, publisher=None, timeout=10, sources=None, debug=None):
        if (not publisher) or (not timeout) or (not sources):
            msg = "Activity tracker initialized without one of the params: pub=%s, timeout=%s, sources=%s" % \
                (publisher, timeout, sources)
            rospy.logerr(msg)
            raise ActivityTrackerException

        self.active = True
        self._lock = threading.Lock()
        self.initialized_sources = []
        self.activity_states = {}
        self.debug = debug
        self.timeout = timeout
        if not self.timeout:
            msg = "You must specify inactivity timeout"
            rospy.logerr(msg)
            raise ActivityTrackerException(msg)
        self.sources = sources
        self.publisher = publisher
        self.publisher.publish(Bool(data=True))  # init the state with True (active)
        self._validate_sources()
        self._init_activity_sources()
        rospy.loginfo("Initialized ActivityTracker: %s" % self)

    def __str__(self):
        string_representation = "<ActivityTracker: sources: %s, initialized_sources: %s, timeout: %s, publisher: %s" % \
            (self.sources, self.initialized_sources, self.timeout, self.publisher)
        return string_representation

    def __repr__(self):
        string_representation = "<ActivityTracker: sources: %s, initialized_sources: %s, timeout: %s, publisher: %s" % \
            (self.sources, self.initialized_sources, self.timeout, self.publisher)
        return string_representation

    def _get_activity_status(self, _):
        """
        ROS service method for retrieving activity state

        """
        with self._lock:
            return self.active

    def activity_callback(self, topic_name=None, state=True, strategy=None):
        """
        ActivitySource uses this callback to set it's state in ActivityTracker

        ActivityTracker keeps state for all ActivitySources with timestamps.

        If all states turned False (inactive) with respect to self.timeout then message is emitted

        If all states turned True (active) then proper message is emitted
        """
        with self._lock:
            if topic_name not in self.activity_states:
                self.activity_states[topic_name] = {"state": state, "time": rospy.get_time()}

            try:
                try:
                    if self.activity_states[topic_name]['state'] == state:
                        rospy.logdebug("State of %s didnt change" % topic_name)
                    else:
                        self.activity_states[topic_name] = {"state": state, "time": rospy.get_time()}
                        rospy.logdebug("Topic name: %s state changed to %s" % (topic_name, state))
                except KeyError:
                    rospy.loginfo("Initializing topic name state: %s" % topic_name)
                    self.activity_states[topic_name] = {"state": state, "time": rospy.get_time()}

                self._check_states()
                return True
            except Exception, e:
                rospy.logerr("activity_callback for %s failed because %s" % (topic_name, e))
                return False

    def _source_is_active(self, source):
        """
        Checks whether source was active for last `self.timeout` seconds
        which basically means that we can consider this source to be active

        Accepts source state dict eg.:
        {"state": True, "time": <unix timestamp> }

        All following constraints need to be met to consider source active:
        a) source is in True (active) state

        All following constraints need to be to consider source inactive:
        b) source is in False (inactive) state
        c) last change of source's state was more than `self.timeout` seconds ago
        """

        now = rospy.get_time()

        if source['state'] is True:
            rospy.logdebug("ActivitySource %s is active" % source)
            return True

        if source['state'] is False and ((now - source['time']) >= self.timeout):
            rospy.logdebug("ActivitySource %s is inactive" % source)
            return False
        else:
            rospy.logdebug("ActivitySource %s is still active" % source)
            return True

    def _check_states(self):
        """
        Emits a proper activity message if all states were in False or True for
        certain period of time
        'state' == True means "active"

        1. check for activity when in inactive state (easiest and fastest)
        2. carefully check for all states


        """
        now = rospy.get_time()
        self.sources_active_within_timeout = {state_name: state for state_name, state in self.activity_states.iteritems() if self._source_is_active(state)}

        if self.sources_active_within_timeout and (not self.active):
            self.active = True
            self.publisher.publish(Bool(data=True))
            rospy.loginfo("State turned from False to True because of state: %s" % self.sources_active_within_timeout)
            rospy.loginfo("States: %s" % self.activity_states)
        elif (not self.sources_active_within_timeout) and self.active:
            self.active = False
            self.publisher.publish(Bool(data=False))
            rospy.loginfo("State turned from True to False because no sources were active within the timeout")
            rospy.loginfo("States: %s" % self.activity_states)
        else:
            rospy.logdebug("Message criteria not met. Active sources: %s, state: %s, activity_states: %s" % (self.sources_active_within_timeout, self.active, self.activity_states))

    def _init_activity_sources(self):
        """
        Turns activity source dictionaries into ActivitySources objects and
        initializes them by adding their state to self.activity_states and
        providing a self.activity_callback for them

        """
        for source in self.sources:
            act = ActivitySource(
                topic=source['topic'], message_type=source['message_type'],
                strategy=source['strategy'], slot=source['slot'],
                value_min=source['value_min'], value_max=source['value_max'],
                callback=self.activity_callback, debug=self.debug)
            self.initialized_sources.append(act)
        return True

    def _validate_sources(self):
        for source in self.sources:
            if type(source) != dict or type(self.sources) != list:
                msg = "sources argument must be a list containing ActivitySource definition dictionaries but was: %s" % self.sources
                rospy.logerr(msg)
                raise ActivitySourceException

    def _get_state(self, header=None):
        """
        Should return boolean activity state based on timeout and sources states
        Used mainly for Service for debugging purposes
        """
        return json.dumps(self.activity_states)

    def poll_activities(self):
        for source in self.initialized_sources:
            source.is_active()
        self._check_states()

    def _sleep_between_checks(self):
        # rospy.sleep(self.timeout)
        pass

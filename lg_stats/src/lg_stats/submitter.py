"""
InfluxDB submission / communication implementations.

"""

import socket

import rospy


class Submitter(object):
    """
    LG Stats - base submission class for sending stats messages.

    """

    def __init__(self):
        raise RuntimeError("Can't instantiate this base class directly.")

    def get_data_for_influx(self, msg):
        raise RuntimeError("Base class method called, not implemented.")

    def write_stats(self, data):
        raise RuntimeError("Base class method called, not implemented.")


class InfluxDirect(Submitter):
    """
    Direct connection to InfluxDB database.

    """
    def __init__(self, host=None, port=None, database=None):
        # keep this dependency here, it will have to be satisfied in case of direct
        # InfluxDB submission (without telegraf) which is secondary scenario
        from influxdb import InfluxDBClient
        self._client = InfluxDBClient(host=host, port=port, database=database)
        rospy.loginfo("InfluxDB (direct) client initialized (%s:%s/%s)." % (host, port, database))

    @staticmethod
    def get_data_for_influx(msg):
        """
        Prepare data for InfluxDB based on the ROS topic message that
        is sent to the debug topic, it contains all stats pertinent details.
        Direct InfluxDB submitter talks JSON.

        """
        influx_dict = dict(measurement=msg.src_topic,
                           tags=dict(application=msg.application,
                                     field_name=msg.field_name,
                                     type=msg.type,
                                     value=msg.value),
                           # timestamp may be added here or will be added by the server
                           #"time": "2015-11-10T23:00:00Z",
                           # fields must be of type float
                           fields=dict(value=0.0))
        return influx_dict

    def write_stats(self, data):
        """
        Send data to InfluxDB database.
        The Python Influx library converts the Python dictionary to
        the default *line_protocol* before submitting to Influx.

        """
        self._client.write_points([data])


class InfluxTelegraf(Submitter):
    """
    Handles connection to InfluxDB via Telegraf submission agent.
    Telegraf accepts data through its tcp_listener.
    It accepts text message in the form of Influx line protocol via plain socket.

    Debugging:
    echo "application,application=someapplication1,type=event value=0.0" | nc localhost 8094
        (sent right to the telegraf tcp_listener port)

    Another format possibility is JSON, was not successful with
    sending JSON, still getting parsing errors.

    """
    def __init__(self, host=None, port=None, database=None):
        self.host = host
        self.port = port
        rospy.loginfo("InfluxDB (telegraf-socket) client initialized (%s:%s)." % (host, port))

    @staticmethod
    def get_data_for_influx(msg):
        msg = ("%s,application=%s,field_name=%s,type=%s,value=%s value=0.0" %
               (msg.src_topic,
                msg.application,
                msg.field_name,
                msg.type,
                msg.value))
        return msg

    def write_stats(self, data):
        """
        Input is a text message in the form of Influx line protocol.

        A socket connection connection and close is performed at each send operation.

        It's impossible to tell whether all data was sent or not.
        """
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            server_address = (self.host, self.port)
            sock.connect(server_address)
            sock.sendall(data)
        except Exception, ex:
            rospy.logerr("Socket error while sending data '%s' to %s, reason: %s" %
                         (data, server_address, ex))
        finally:
            sock.close()
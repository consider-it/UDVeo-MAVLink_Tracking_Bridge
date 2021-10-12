#!/usr/bin/env python3
"""
UDVeo - MAVLink Tracking Bridge

Connector application translating between MAVLink and the USSP prototype for Network-based Remote
Identification (Tracking) of UAS using the MAVLink UTM_GLOBAL_POSITION message.

A settings file (YAML) with the credentials is required.

Author:    Jannik Beyerstedt <beyerstedt@consider-it.de>
Copyright: (c) consider it GmbH, 2021
"""

import argparse
import logging
import sys
import json
import ssl
import math
from typing import Tuple
import yaml
import pika
import paho.mqtt.client as paho
import pymavlink.mavutil as mavutil
from pymavlink.dialects.v10 import common as mavlink1

OWN_SYSID = 255
OWN_COMPID = 0
UDP_CONNECT_TIMEOUT = 10


def setup() -> Tuple[dict, bool, bool]:
    """Parse config file and CLI options; Return config dict"""
    parser = argparse.ArgumentParser(description='MAVLink Network Remote ID (Tracking) Bridge')
    parser.add_argument("-c", "--config", default='settings.yml',
                        help="path to settings file")
    parser.add_argument("-d", "--device",
                        help="connection address, e.g. tcp:$ip:$port, udpin:$ip:$port")
    parser.add_argument("-v", "--verbosity", action="count",
                        help="increase output and logging verbosity")
    args = parser.parse_args()

    if args.verbosity == 2:
        logger.setLevel(logging.DEBUG)
    elif args.verbosity == 1:
        logger.setLevel(logging.INFO)
    else:
        logger.setLevel(logging.WARNING)

    amqp_conf_valid = False
    mqtt_conf_valid = False
    mavlink_config_exists = False
    with open(args.config) as file:
        data = yaml.load(file, Loader=yaml.FullLoader)

        # all amqp keys are required for a valid connection
        amqp_conf_valid = False
        if 'amqp' in data:
            amqp_keys = ['host', 'username', 'password', 'queue']
            amqp_conf_valid = True
            for key in amqp_keys:
                if key not in data['amqp']:
                    logger.error("Key \'%s\' missing from AMQP config", key)
                    amqp_conf_valid = False

        # all mqtt keys are required for a valid connection
        mqtt_conf_valid = False
        if 'mqtt' in data:
            mqtt_keys = ['host', 'port', 'topic']
            mqtt_conf_valid = True
            for key in mqtt_keys:
                if key not in data['mqtt']:
                    logger.error("Key \'%s\' missing from MQTT config", key)
                    mqtt_conf_valid = False

        if not amqp_conf_valid and not mqtt_conf_valid:
            logger.error("A valid AMQP or MQTT config is required")
            sys.exit(1)

        # mavlink config is optional
        mavlink_config_exists = False
        if 'mavlink' in data:
            if 'device' in data['mavlink']:
                mavlink_config_exists = True

    if args.device is not None:
        data['mavlink']['device'] = args.device
    elif not mavlink_config_exists:
        logger.error("No MAVLink device specified in config or CLI options")
        parser.print_help()
        sys.exit(1)

    return data, amqp_conf_valid, mqtt_conf_valid


def run(data: dict, enable_amqp: bool, enable_mqtt: bool):
    """Run the MAVLink to AMQP bridge with the provided config dict"""
    # SETUP

    # open the AMQP connection
    amqp_channel = None
    if enable_amqp:
        credentials = pika.PlainCredentials(data['amqp']['username'], data['amqp']['password'])
        # context = ssl.create_default_context()
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        context.check_hostname = False  # TODO: testing only!!!
        context.verify_mode = ssl.CERT_NONE  # TODO: testing only!!!
        ssl_options = pika.SSLOptions(context)

        logger.info("Starting AMQP connection to %s", data['amqp']['host'])
        parameters = pika.ConnectionParameters(host=data['amqp']['host'],
                                               credentials=credentials, ssl_options=ssl_options)

        connection = pika.BlockingConnection(parameters)
        amqp_channel = connection.channel()

    # open the MQTT connection
    mqtt_client = None
    if enable_mqtt:
        logger.info("Starting MQTT connection to %s:%s",
                    data['mqtt']['host'], data['mqtt']['port'])
        mqtt_client = paho.Client()
        mqtt_client.connect(data['mqtt']['host'], port=data['mqtt']['port'])
        mqtt_client.loop_start()

    # open the MAVLink connection
    try:
        logger.info("Starting MAVLink connection to %s", data['mavlink']['device'])
        mav = mavutil.mavlink_connection(
            data['mavlink']['device'], source_system=OWN_SYSID, source_component=OWN_COMPID)
    except OSError:
        logger.error("MAVLink connection failed, exiting")
        sys.exit(-1)

    # when udpout, start with sending a heartbeat
    if data['mavlink']['device'].startswith('udpout:'):
        i = 0
        logger.info("UDP out: sending heartbeat to initilize a connection")
        while True:
            mav.mav.heartbeat_send(OWN_SYSID, OWN_COMPID, base_mode=0,
                                   custom_mode=0, system_status=0)
            i += 1

            msg = mav.recv_match(type='HEARTBEAT', blocking=True, timeout=1)
            if msg is not None:
                break

            if i >= UDP_CONNECT_TIMEOUT:
                logger.error("UDP out: nothing received, terminating")
                sys.exit(-1)

            logger.debug("UDP out: retrying heartbeat")

    # RUN
    altitude_offset = 0
    if 'altitudeOffsetMeters' in data:
        altitude_offset = data['altitudeOffsetMeters']

    set_flying_when_grounded = False
    if 'setFlyingWhenGrounded' in data:
        set_flying_when_grounded = data['setFlyingWhenGrounded']

    while True:
        # wait for message from MAVLink
        msg = mav.recv_match(type='UTM_GLOBAL_POSITION', blocking=True)
        logger.debug("Message from %d/%d: %s", msg.get_srcSystem(), msg.get_srcComponent(), msg)

        # convert to UDVeo json
        utm_tracking_data = {"uavId": "",
                             "flightOperationId": "USSP-HH-unknwon",
                             "timeStamp": 0.0,  # (float) seconds unix time
                             "coordinate": {
                                 "type": "Point",
                                 # (float) degrees east (longitude, latitude)
                                 "coordinates": [10.0, 53.0],
                             },
                             "heading": 0,  # (float) degree
                             "altitudeInMeters": 0.0,
                             "speedInMetersPerSecond": 0.0,
                             "isFlying": False
                             }

        # fill in data from UTM_GLOBAL_POSITION
        uav_id_string = ""
        for byte in msg.uas_id:
            uav_id_string += format(byte, "02x")

        velocity = math.sqrt(msg.vx * msg.vx + msg.vy * msg.vy) / 100  # cm/s -> m/s
        heading = math.atan2(msg.vy, msg.vx) / math.pi * 180  # degrees
        if heading < 0:
            heading += 360

        utm_tracking_data['uavId'] = "D2X-" + uav_id_string[-8:]
        utm_tracking_data['timeStamp'] = msg.time / 1000000  # us -> s
        utm_tracking_data['coordinate']['coordinates'][1] = msg.lat / 10000000  # degE7 -> deg
        utm_tracking_data['coordinate']['coordinates'][0] = msg.lon / 10000000  # degE7 -> deg
        utm_tracking_data['altitudeInMeters'] = msg.alt / 1000 + altitude_offset  # mm -> m
        utm_tracking_data['heading'] = heading
        utm_tracking_data['speedInMetersPerSecond'] = velocity  # cm/s -> m/s

        utm_tracking_data['isFlying'] = msg.flight_state != mavlink1.UTM_FLIGHT_STATE_GROUND and msg.flight_state != mavlink1.UTM_FLIGHT_STATE_UNKNOWN
        if set_flying_when_grounded:  # override for testing purposes
            utm_tracking_data['isFlying'] = True

        fly_string = "flying" if utm_tracking_data['isFlying'] else "grounded"
        logger.info("Tracked '%s': %+9.4f N, %+9.4f E at %+6.2f m %s %4.2f m/s @ %3.0f°",
                    utm_tracking_data['uavId'],
                    utm_tracking_data['coordinate']['coordinates'][1],
                    utm_tracking_data['coordinate']['coordinates'][0],
                    utm_tracking_data['altitudeInMeters'],
                    fly_string,
                    utm_tracking_data['speedInMetersPerSecond'],
                    utm_tracking_data['heading']
                    )

        json_string = json.dumps(utm_tracking_data)

        # send via AMQP
        if enable_amqp:
            try:
                amqp_channel.basic_publish(
                    exchange='', routing_key=data['amqp']['queue'], body=json_string)
            except pika.exceptions.UnroutableError:
                logger.warning("AMQP message routing failed")
            except pika.exceptions.NackError:
                logger.warning("AMQP message not acknowledged")

        # send via MQTT
        if enable_mqtt:
            mqtt_client.publish(data['mqtt']['topic'], payload=json_string, qos=0, retain=False)


if __name__ == "__main__":
    LOG_FORMAT = '%(asctime)s %(levelname)s:%(name)s: %(message)s'
    LOG_DATEFMT = '%Y-%m-%dT%H:%M:%S%z'
    logging.basicConfig(format=LOG_FORMAT, datefmt=LOG_DATEFMT, level=logging.INFO)
    logger = logging.getLogger()

    config, amqp_valid, mqtt_valid = setup()
    run(config, amqp_valid, mqtt_valid)

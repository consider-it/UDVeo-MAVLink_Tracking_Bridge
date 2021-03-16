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
import yaml
import pika
import ssl
import pymavlink.mavutil as mavutil

OWN_SYSID = 255
OWN_COMPID = 0
UDP_CONNECT_TIMEOUT = 10


if __name__ == "__main__":
    log_format = '%(asctime)s %(levelname)s:%(name)s: %(message)s'
    log_datefmt = '%Y-%m-%dT%H:%M:%S%z'
    logging.basicConfig(format=log_format, datefmt=log_datefmt, level=logging.INFO)
    logger = logging.getLogger()

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

    with open(args.config) as f:
        data = yaml.load(f, Loader=yaml.FullLoader)

        # all amqp keys are required
        AmqpConfigIsValid = False
        if 'amqp' in data:
            amqpKeys = ['host', 'username', 'password', 'queue']
            AmqpConfigIsValid = True
            for key in amqpKeys:
                if key not in data['amqp']:
                    logger.error("Key \'%s\' missing from AMQP config", key)
                    AmqpConfigIsValid = False

        if not AmqpConfigIsValid:
            logger.error("AMQP config section missing or incomplete in settings file")
            sys.exit(1)

        # mavlink config is optional
        MavlinkConfigExists = False
        if 'mavlink' in data:
            if 'device' in data['mavlink']:
                MavlinkConfigExists = True

    if args.device is not None:
        data['mavlink']['device'] = args.device
    elif not MavlinkConfigExists:
        logger.error("No MAVLink device specified in config or CLI options")
        parser.print_help()
        sys.exit(1)

    # SETUP
    # open the AMQP connection
    credentials = pika.PlainCredentials(data['amqp']['username'], data['amqp']['password'])
    # context = ssl.create_default_context()
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.check_hostname = False  # TODO: testing only!!!
    context.verify_mode = ssl.CERT_NONE  # TODO: testing only!!!
    ssl_options = pika.SSLOptions(context)

    # open the connection
    parameters = pika.ConnectionParameters(host=data['amqp']['host'],
                                           credentials=credentials, ssl_options=ssl_options)

    connection = pika.BlockingConnection(parameters)
    channel = connection.channel()

    # open the MAVLink connection
    try:
        mav = mavutil.mavlink_connection(
            data['mavlink']['device'], source_system=OWN_SYSID, source_component=OWN_COMPID)
    except OSError:
        logger.error("MAVLink connection failed, exiting")
        sys.exit(-1)

    # # when udpout, start with sending a heartbeat
    # if data['mavlink']['device'].startswith('udpout:'):
    #     i = 0
    #     logger.info("UDP out: sending heartbeat to initilize a connection")
    #     while True:
    #         mav.mav.heartbeat_send(OWN_SYSID, OWN_COMPID, base_mode=0,
    #                                custom_mode=0, system_status=0)
    #         i += 1

    #         msg = mav.recv_match(type='HEARTBEAT', blocking=True, timeout=1)
    #         if msg is not None:
    #             break

    #         if i >= UDP_CONNECT_TIMEOUT:
    #             logger.error("UDP out: nothing received, terminating")
    #             sys.exit(-1)

    #         logger.debug("UDP out: retrying heartbeat")

    # RUN
    while True:
        msg = mav.recv_match(type='UTM_GLOBAL_POSITION', blocking=True)
        logger.debug("Message from %d/%d: %s", msg.get_srcSystem(), msg.get_srcComponent(), msg)

        # TODO: convert to json

        try:
        channel.basic_publish(exchange='', routing_key=data['amqp']['queue'],
                              body='{"uavId":"simD1","flightOperationId":"USSP-HH-5","timeStamp":1614699998.863000000,"coordinate":{"easting":9.933075488056465,"northing":53.505255593047735,"epsgCode":4326},"altitudeInMeters":1.0,"speedInMetersPerSecond":0.0,"isFlying":true}')
        except pika.exceptions.UnroutableError:
            logger.warning("AMQP message routing failed")
        except pika.exceptions.NackError:
            logger.warning("AMQP message not acknowledged")

        logger.info("Message sent")

        # connection.close()

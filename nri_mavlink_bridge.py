#!/usr/bin/env python3
"""
UDVeo - MAVLink Tracking Bridge

Connector application translating between MAVLink and the USSP prototype for Network-based Remote
Identification (Tracking) of UAS using the MAVLink UTM_GLOBAL_POSITION message.

Author:    Jannik Beyerstedt <beyerstedt@consider-it.de>
Copyright: (c) consider it GmbH, 2021
"""

import argparse
import logging
import sys
import json
import pymavlink.mavutil as mavutil

OWN_SYSID = 255
OWN_COMPID = 0
UDP_CONNECT_TIMEOUT = 10


if __name__ == "__main__":
    log_format = '%(asctime)s %(levelname)s:%(name)s: %(message)s'
    log_datefmt = '%Y-%m-%dT%H:%M:%S%z'
    logging.basicConfig(format=log_format, datefmt=log_datefmt, level=logging.INFO)
    logger = logging.getLogger()

    parser = argparse.ArgumentParser(description='TODO Program Title')
    parser.add_argument("-d", "--device", required=True,
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

    # SETUP
    # open the connection
    try:
        mav = mavutil.mavlink_connection(
            args.device, source_system=OWN_SYSID, source_component=OWN_COMPID)
    except OSError:
        logger.error("MAVLink connection failed, exiting")
        sys.exit(-1)

    # # when udpout, start with sending a heartbeat
    # if args.device.startswith('udpout:'):
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

# UDVeo MAVLink Tracking Bridge
Network-based Remote Identification (Tracking) of UAS using the MAVLink UTM_GLOBAL_POSITION message. Connector application translating between MAVLink and the USSP prototype.


## Installation
Make sure, that all build tools and python C headers are installed:
```shell
sudo apt install build-essential python3-dev
```

Clone this repository (create a venv, if you like) and install all requirements:
```shell
git clone -b feature/python https://office.consider-ip.com/gitea/UDVeo/MAVLink-Tracking-Bridge.git
cd MAVLink-Tracking-Bridge
pip3 install -r requirements.txt
```


## Usage
Date can be published to an AMQP broker and/or a MQTT broker.
One of both sections must exist in the config file, otherwise the application won't start.

Create a settings file with the AMPQ and/or MQTT server credentials and MAVLink connection, like this (default name: `./settings.yml`):
```yaml
amqp:
  host: localhost
  username: foobar
  password: 1234
  queue: testqueue

mqtt:
  host: localhost
  port: 1883
  topic: testtopic

mavlink:
  device: udpin:0.0.0.0:14560
  #device: /dev/cu.foobar

# altitudeOffsetMeters: 0
# setFlyingWhenGrounded: False
```

Run:
```shell
python3 nri_mavlink_bridge.py 
```

Command line parameters will override the values from the settings file.
Use `-h` for the list of available parameters.

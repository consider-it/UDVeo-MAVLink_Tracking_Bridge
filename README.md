# UDVeo MAVLink Tracking Bridge
Network-based Remote Identification (Tracking) of UAS using the MAVLink UTM_GLOBAL_POSITION message. Connector application translating between MAVLink and the USSP prototype.


## Installation
Clone this repository (create a venv, if you like) and install all requirements:
```shell
git clone -b feature/python https://office.consider-ip.com/gitea/UDVeo/MAVLink-Tracking-Bridge.git
cd MAVLink-Tracking-Bridge
pip3 install -r requirements.txt
```


## Usage
Create a settings file with the AMPQ server credentials and MAVLink connection, like this (default name: `./settings.yml`):
```yaml
amqp:
  host: localhost
  username: foobar
  password: 1234
  queue: testqueue

mavlink:
  device: udpin:0.0.0.0:14560
```

Run:
```shell
python3 nri_mavlink_bridge.py 
```

Command line parameters will override the values from the settings file.
Use `-h` for the list of available parameters.

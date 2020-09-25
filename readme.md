# HP1000 - a driver for HP1000 and clones including WS1001 and XC0422
Copyright 2017-2020 Susan Mackay

# Introduction
The HP1000 driver communicates directly with the weather station console via 
WiFi.

Note: This version requires WeeWx V4.1.1 or above and therefore Python 3.

When the driver is started, it will make contact with the weather station and
try to retrieve any archive records (make by the weather station at the interval
set by the "Interval" setup parameter) before reading the current data at 
regular intervals. If weeWx has not been used before, this can take a while
(about an hour for each year in the archive) but it means that the weather
station historical data is made avialable to weeWx.

The normal generation of  html files will be delayed while weeWx performs the 
catch up process, but it means that the data will include the period while weeWx 
was not working but the weather station was still logging data.

## Parameter Units
The HP1000 weather consoles can display wind, rain and similar properties
using a selection of units (set in the console's "Setup" panel). For example, 
wind speed' can be in m/s, km/h, knots, mph and even Beaufort scale numbers. The 
driver will determine the currently selected units when it connects with the 
console

## Network
The HP1000 (and similar 'clone' devices such as the WS1001 and XC0422 weather 
stations) communicates via WiFi to the local network to pass data to Weather 
Underground (or whatever other weather upload service is used). As such the 
weather console will have an IP address on the local WiFi network.

The driver will communicate with the weather console via this WiFi link. In 
order to find the weather station on the network, the driver will send 
'broadcast' messages until it receives a response from the weather console. The
response will tell the driver the weather station's IP address and form then on
all communication will be direct between the driver and the weather station.

If communication is lost with the weather station, the above process is repeated
until it is reestablished.

## Log Messages
The driver will output messages to the system log as it tries to establish 
connection to the weather station console and if communication is lost. No 
messages are sent by the driver during  normal operation. All messages have the 
text 'HP1000' in them which allows easy searching of the log file.

## Limitations
### Unit Selection
The driver only requests the parameter units form the console when a connection
is established. Therefore, if you change the unit for a parameter, the weeWx
program must be restarted. Otherwise the information form the console will be
misinterpreted.

### Network
In order to find the weather console, the driver issues UDP 'broadcast' 
messages. While it is possible for routers to pass these packets between
subnets, the need to be suitably configured (which is beyond the scope of these
notes). Therefore it is recommended that the weather console and the computer
running weeWx and this driver be on the same subnet.

If you have the 'netifaces' Python package installed, then the driver will
try to find the correct broadcast address of the "default" interface. (The
default interface generally the one your computer uses to communicate with
the rest of the Internet.)

If you do not have the 'netifaces' package installed then you will need to
define the broadcast address mask as a configuration item in the 
'[HP1000]' section of the 'weewx.conf' file - it takes the form:

    ip_address_mask = "192.168.1.255"
or

    ip_address_mask = "10.1.255.255"

In other words, it is the main network address with '255' added as the final
component or components, depending on the addressing scheme used on your 
computer.

The driver will attempt to communicate with the weather station as soon as 
weeWx requests a 'loop' packet. This means that the driver can request a packet 
every few seconds (depending on how fast the weather station responds to each 
request) which can lead to a volume of network traffic. Depending on the network
setup and other uses of the network, this may or may not be an issue.

Be default the 'loop_delay' configuration parameter is set to 15 seconds which 
means that there will be a minimum of 15 seconds between requests for data from 
the weather station. This parameter can be adjusted up or down as desired with 
a value of 0 meaning that packets will be requested as frequently as possible.

## Testing
The driver can be run stand-alone and without connection to a weather station 
console by following the instructions for runing a stand-alone driver in the 
weeW3x documentation.

# Pre-requisites

The HP1000 driver has been tested using weeWx V4.1.1 and uses Python 3. It might work on earlier 
versions but this has not been tested and is not guaranteed.
Similarly, it might work with later versions but this has not been tested.

## Active Network Required
An active network is required before the HP1000 driver can access the weather 
station console. This can be an issue when weeWx is run as a daemon which means 
that it will be started as the computer system boots.

weeWx can be set up to handle this situation is one of two ways.

**Note** Editing the weewx.conf file is the recommended option

### Edit the weewx.conf file
weeWx has a built-in mechanism to handle network failures. In the weewx.conf file add in the line

    loop_on_init = True

This line can be added right at the top in the same area where the 'debug' and 
WEEWX_ROOT parameters are defined.

In this case, the HP1000 driver will retry a network access the number of times 
set by the 'max_retry' driver configuration parameter (default is 3) and it will 
then wait for 60 seconds and repeat the process indefinitely until network 
access is maintained.

This process will also be used if the network access is lost at any time after
weeWx is operating normally.

### Edit the Daemon startup file
With this option, you tell the daemon to delay starting until an active network 
is available. The file you need to edit depends on whether you are using SysV or 
systemctl to control the computer. This can be done by editing/adding the appropriate file as outlined below.

#### SysV
    Required-Start: $local_fs ... _$network_ ...
    Required-Stop: $local_fs ... _$network_ ...

#### systemctl
    Requires=network-online.target
    After=network-online.target
    Restart=always
    RestartSec=60

**Note**: there can be multiple 'Requires' and 'After' lines in the control 
file.

The last two lines ensure that any crash of weeWx will cause the program to be 
restarted after a 60 second pause. This applies to errors other than the network 
access one discussed here.

# Installation instructions
Please consider the information in the 're-requisites' section.

1) run the installer:

    sudo cd <path to weewx directory>
    sudo python ./bin/wee_extension --install <path to file>/HP1000
    sudo python ./bin/wee_config --reconfigure

The last command will (eventually) list all of the known drivers. Select the 
number next to 'HP1000'.

2) Start weeWx:

    sudo /etc/init.d/weewx enable
    sudo /etc/init.d/weewx start

or 

    sudo systemctl daemon-reload
    sudo systemctl weewx enable
    sudo systemctl weewx start

3) To restart weewx:

    sudo /etc/init.d/weewx stop
    sudo /etc/init.d/weewx start

or 

    sudo systemctl restart weewx

#
#    Copyright (c) 2017 Susan Mackay
#       acknowledging that this driver code originated from and 
#       is structured in a similar way to the Weewx 'Simulator' driver code
#       that carries the following line:
#    Copyright (c) 2009-2015 Tom Keffer <tkeffer@gmail.com>
#
#
"""hp1000 driver for the weewx weather system

This driver communicates with the HP1000/WS1001/XC0422 and whatever other clone
weather stations respond over the LAN to the 'easyweather' protocol.

Communication starts with a UDP IP broadcast on the local subnet to port 6000 to
see if the weather station responds. The broadcast packet is structured as:

Offset  Value           Structure       Comment
0x00    PC2000          8 byte string   Identifies the calling station
0x08    SEARCH          8 byte string   Command
0x10    nulls           24 null bytes   I think there could be structure here but
                                        sending nulls works!
    
(NB: All strings are null padded if required)


The weather station returns a packet structured as:

Offset  Value           Structure       Comment
0x00    HP2000          8 byte string   Name of the seather station
0x08    SEARCH          8 byte string   Command
0x10                    8 byte string   Unknown
0x18                    16 bytes        Not yet deciphered
0x28    text            24 byte string  MAC address of the weather station
0x40    text            16 byte string  IP address of the weather station


The last item is the one that we are after as then then make an TCP connection
to port 6500 on that address for all further communications.

All packets have the same basick structure: the 8-byte (null terminated) sending
device name, the 8 byte command (READ - sent to the weather station requesting
data; WRITE - the response from the wreather station with the requested data)
and a 12-byte sub-command with the type of data to be read/sent. This is followed
by what appears to be random characters but sending nulls does not seem to affect
things.

READ packets are always 40 bytes and WRITE packets vary in length depending on the
data but has a 32-byte header (structured as above).

The weather station will send data using the unit selection in the 'set up' screen
(e.g temperature in degrees Fahrenheit or Celsius). Therefore you need to know what
conversions (if any) are needed to build up the LOOP record. 

The driver follows the (nearly) universal convention and uses the Metric (METRICWX) 
system for the LOOP packet and so will convert al values to SI units.

To find out what units are being sent by the weather staiton, send a "SETUP" command and 
interpret the response as follows (after the 32-byte header):

Offset  Value       Structure   Comment
0x20    unknown     16 bytes    Yet to be deciphered
0x30    Time        1 byte      1 = 'H:mm:ss', 2="h:mm:ss AM", 4='AM h:mm:ss'
0x31    Date        1 byte      16 = 'DD-MM-YYYY', 32 = 'MM-DD-YYYY', 64 = 'YYYY-MM-DD'
0x32    Temperature 1 byte      0 = Celsius, 1 = Fahrenheit
0x33    Pressure    1 byte      0 = hPa, 1 = inHg, 2 = mmHg
0x34    Wind speed  1 byte      0 = m/s, 1 = km/h, 2 = knots, 3 = mph, 4 = Beaufort, 5 = ft/s
0x35    Rainfall    1 byte      0 = mm, 1 = in
0x36    Solar rad   1 byte      0 = lux, 1 = fc, 2=W/m^2
0x37    Rain display1 byte      0 = rain rate, 1 = daily, 2 = weekly, 3 = monthly, 4 = yearly
0x38    Graph time  1 byte      0 = 12h, 1 = 24h, 2 = 48h, 3 = 72h
0x39    Barometer   1 byte      0 = absolute, 1 = relative
0x3a    Weather     1 byte      number
0x3b    Storm       1 byte      number
0x3c    Current     1 byte      0 = sunny, 1 = partly cloudy, 2 = cloudy, 3 = raim. 4 = strom
0x3d    Reset       1 byte      Month for yearly rain reset, 1 = Jan, 2 = Feb...
0x3e    Update      1 byte      Update interval in minutes

Many of these (from offset 0x37 on) are of little interest for the driver byte the 
temperature, pressure, wind speed, rain and solar radiaiton units are all used.


The main data packet that is fetched is the NOWRECORD and it has the following structure
(again after the 32 byte header):

Offset  Value       Structure   Comment
0x20    unknown     8 bytes     Yet to be deciphered
0x28    Wind dir    2 bytes     Wind direction (in degrees from North = 0) [4]
0x2a    inHumidity  1 byte      Inside humidity [5]
0x2b    outHumidity 1 byte      Outside humidity [6]
0x2c    inTemp      4 bytes     Inside temperature (floating point) [7]
0x30    pressure    4 bytes     Relative pressure (floating point) [8]
0x34    barometer   4 bytes     Absolute pressure (floating point) [9]
0x38    outTemp     4 bytes     Outside temperature (floating point) [10]
0x3c    dewPoint    4 bytes     Dew Point tempperature (floating point) [11]
0x40    windChill   4 bytes     Wind Chill temperature (floating point) [12]
0x44    windSpeed   4 bytes     Wind speed (floating point) [13]
0x48    windGust    4 bytes     Wind Gust (floating point) [14]
0x4c    rainRate    4 bytes     Rain rate (floating point) [15]
0x50    dailyRain   4 bytes     Daily rain (floating point) [16]
0x54    weeklyRain  4 bytes     Weekly rain (floating point) [17]
0x58    monthlyRain 4 bytes     Monthly rain (floating point) [18]
0x5c    yearlyRain  4 bytes     Yearly rain (floating point) [19]
0x60    radiation   4 bytes     Current solar radiation(floating point) [20]
0x64    UVI         1 byte      UV Index [21]
0x65                1 bytes     Unknown [22]
0x66                2 bytes     Unkonwn [23]


When the driver starts up, it checks to see if the weather station has data 
available for the time it has been off. Weewx will call the 'genStartupRecords'
funciton passing the timestamp of the last archve record.
There are two main cases to account for:
- this is the first access by Weewx - the timestamp will by None and we need
  to get all of the records available in the weather station
- we are restarting and the passed timestamp contains a valid value - we need
  to find the corresponding record in the weather station
  
The HISTORY_FILE command will return a packet strcutured (after the header) as:

Offset  Value       Structure   Comment
0x20    packetSize  2 bytes     Total length of the packet (including the header)
0x22                2 bytes
0x24                2 bytes
0x26                2 bytes
0x28    Year        16 bytes    8 entries (2 bytes each) with the year containing valid data
0x38    RecCount    32 bytes    8 entries (4 bytes each) with the number of records for the year

The years are in desceding order (e.g. 2017 then 2016 etc.) with 0 for any year without
data. Thre RecCount values correspond to the years (e.g. the first one is for the latest
year, then 2nd one for the previous year etc.)

From the timestamp of the last known good Weewx record, the driver finds the corresponding 
year index and then the record number. It does a binary search through the history data
records (retrieving one at a time) until it finds a record that "matches".

Matching here is a bit complex in that it is not likely that the Weewx timestamp will
correspond to any weather station record. Therefor the binary search ends when the 
upper and lower indicies converge. This means that we shoud have an index of the
first record to retrieve that will have a timestamp that is not less than the Weewx 
timestamp.

The driver then starts reading HISTORY_DATA records, 100 at a time if possible) from 
the starting index to the last record for the year. It then moves to the next year 
(starting with record index 0) until it runs out of data.

All of this can take a while (my setup seems to take a bit over an hour for each year's
worth of data) and so the last HISTORY_DATA record timestamp is used to repeat the whole
process of reading the archive records. Eventually this will result in no more records
being available and the 'genStartupRecords' fnciton completes and Weewx starts requesting
loop packets.

All HISTORY_DATA records appear to be in SI units without regard for the 'Set up' screen
settings, except for Solar Radiaion which is in Lux.

The HISTORY_DATA records are structured (after the header) as:

Offset  Value       Structure   Comment
0x20    dateTime    8 bytes     Date/time of the record in 100nSec increments since 1/1/1601
0x28    inTemp      2 bytes     Indoor temperature (x10 - 17.3 is passed as 173)
0x2a    inHumidity  2 bytes     Indoor humidity
0x2c    pressure    2 bytes     Absolute pressure (x10)
0x2e    barometer   2 bytes     Relative pressure (x10)
0x30    outTemp     2 bytes     Outdoor tempuerature (x10)
0x32    outHumidity 2 bytes     Outdoor humidity
0x34    dewPoint    2 bytes     Dew point temperature (x10)
0x36    windChill   2 bytes     Wind chill temperature (x10)
0x38    ???         2 bytes     This could be the heat index value but often shown as 0x00ff
0x3a    windSpeed   2 bytes     Wind speed (x10)
0x3c    windGust    2 bytes     Wind Gust (x10)
0x3e    windDir     2 bytes     Wind direction
0x40    RainRate    4 bytes     Rain rate (4 byte integer)
0x44    DailyRain   4 bytes     Daily rain (4 byte integer)
0x48    weeklyRain  4 bytes     Weekly rain (4 byte integer)
0x4c    monthlyRain 4 bytes     Monthly rain (4 byte integer)
0x50    yearlyRain  4 bytes     Yearly Rain (4 byte integer)
0x54    uv          4 bytes     UV (4 byte integer) in uW/cm^2
0x58    radiation   4 bytes     Solar radiation (4 byte integer) in lux X10

"""

import math
import time
import datetime

import weedb
import weewx.drivers
import weeutil.weeutil
from weewx.units import convertStd
from weeutil.weeutil import timestamp_to_string

from signal import signal, SIGPIPE, SIG_DFL

import syslog
import sys
import socket
import struct

DRIVER_NAME = 'HP1000'
DRIVER_VERSION = "1.3"

UDP_BROADCAST_PORT = 6000
TCP_PORT = 6500


def loader(config_dict, engine):
    station = HP1000Driver(**config_dict[DRIVER_NAME])
    return station


def logmsg(level, msg):
    syslog.syslog(level, 'HP1000: %s' % (msg))


def logdbg(msg):
    logmsg(syslog.LOG_DEBUG, msg)


def loginf(msg):
    logmsg(syslog.LOG_ERR, msg)


def logerr(msg):
    logmsg(syslog.LOG_ERR, msg)


class HP1000Driver(weewx.drivers.AbstractDevice):
    """HP1000 Driver"""

    def __init__(self, **stn_dict):
        """Initialize the HP1000 driver"""
        self.ws_name = "HP1000"

        loginf('HP1000 Starting')

        self.internal_test_mode = False
        self.startup_count = 5

        try:
            self.ip_address_mask = stn_dict['ip_address_mask']
            loginf("Using user-defined broadcast mask - %s" % self.ip_address_mask)
        except KeyError, e:
            try:
                import netifaces
                gateway_interface = netifaces.gateways()['default'][netifaces.AF_INET][1]
                self.ip_address_mask = netifaces.ifaddresses(gateway_interface) \
                        [netifaces.AF_INET][0]['broadcast']
                loginf('Using "netifaces" to determine broadcast mask')
            except ImportError:
                self.ip_address_mask = None

        if self.ip_address_mask is None:
            raise Exception(
                "Required parameter 'ip_address_mask' has not been specified or could not be determined")

        # Save the configuration parameters
        self.retry_count = int(stn_dict.get('retry_count', 5))
        self.socket_timeout = float(stn_dict.get('socket_timeout', 5))
        self.loop_delay = float( stn_dict.get('loop_delay', None))
        self.retry_wait = int(stn_dict.get('retry_wait', 5))
        self.max_retry = int(stn_dict.get('max_retry', 3))

        self.last_rain_value = None
        self.last_rain_time = None

        loginf('Address Mask = %s' % self.ip_address_mask)
        loginf('Retry count = %f' % self.retry_count)
        loginf('Socket timeout = %f' % self.socket_timeout)
        if self.loop_delay is None:
            loginf('No loop delay')
        else:
            loginf('Loop delay = %f' % self.loop_delay)
        loginf('Retry Wait = %f' % self.retry_wait)
        loginf('Max Retry = %f' % self.max_retry)

        # Show that we are not connected to a weather station
        self.ws_socket = None

    def string_to_null_padded(self, source, max_length, padd_char='\0'):
        # Create a byte array
        passed_string = source.ljust(max_length, '\0')
        return passed_string

    def create_cmd_string(self, cmd="READ", argument="NOWRECORD"):
        # Create the complete packet
        cmd_packet = '{0:<8s}{1:<8s}{2:<12s}'.format(
            self.string_to_null_padded('PC2000', 8),
            self.string_to_null_padded(cmd, 8),
            self.string_to_null_padded(argument, 12))
        cmd_packet = self.string_to_null_padded(cmd_packet, 40)

        return cmd_packet

    def convert_units(self, source, target):
        """Suppress errors when the conversion cannot occcur
        such as when the source and target unit are the same - it happens a lot
        in this code"""
        try:
            result = convertStd(source, target)
        except:
            result = source
        return result
        
    def connectToWeatherStation(self):
        # Not sure why but this seems to be needed on my Raspberry Pi
        signal(SIGPIPE,SIG_DFL)
        network_retry_count = self.max_retry   # Local network failure retry counter
        
        while self.ws_socket is None:
            # Search for a weather station on the specified subnet
            if not self.internal_test_mode:
                # Broadcast for a weather station
                sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM,
                                     socket.IPPROTO_UDP)
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
                sock.settimeout(self.socket_timeout)
                bcData = "PC2000\0\0SEARCH\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0"
                retry_counter = self.retry_count
                sender_addr = None
                while True:
#                        loginf('Sending broadcast request')
                    try:
                        sock.sendto(bcData,
                                    (self.ip_address_mask, UDP_BROADCAST_PORT))
                    except socket.error:
                        network_retry_count -= 1
                        if network_retry_count > 0:
                            # Try accessing the network again after a short break
                            time.sleep(self.retry_wait)
                            break
                        else:
                            # Run out of attempts
                            raise weewx.RetriesExceeded
                    try:
                        # Receive the response form the weather station
                        data, sender_addr = sock.recvfrom(512)
#                            loginf( 'Received ack from {0}'.format(sender_addr))
                        break
                    except socket.timeout:
                        retry_counter -= 1
                        #                            loginf('Timeout')
                        if retry_counter == 0:
                            sender_addr = None
                            loginf('Timed out too many times')
                            break
                    except socket.error:
                        network_retry_count -= 1
                        if network_retry_count > 0:
                            # Try accessing the network again after a short break
                            time.sleep(self.retry_wait)
                            break
                        else:
                            # Run out of attempts
                            raise weewx.RetriesExceeded                        
                    except Exception as e:
                        sender_addr = None
#                            loginf('Unknown error: {0}'.format(e))
                        break
                sock.close()

                # make sure we found something
                if sender_addr is None:
                    continue

                # Get the data sent back by the weather station
                self.ws_name = data[0:8].decode().rstrip('\0')
                self.ws_MAC_address = data[40:64].decode().rstrip('\0')
                self.ws_IP_address = data[64:80].decode().rstrip('\0')

#                    loginf( 'WS Name = %s' % self.ws_name)
#                    loginf( 'MAC Address = %s' % self.ws_MAC_address)
#                    loginf( 'IP Address = %s' % self.ws_IP_address)

                # Connect to the weather station
                self.ws_socket = None
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                sock.settimeout(self.socket_timeout)
                try:
                    sock.bind(("0.0.0.0", TCP_PORT))
                except socket.error:
                    network_retry_count -= 1
                    if network_retry_count > 0:
                        sock.close()
                        # Try accessing the network again after a short break
                        sleep(self.retry_wait)
                        continue
                    else:
                        # Run out of attempts
                        raise weewx.RetriesExceeded

                while True:
                    sock.listen(5)
                    try:
                        # Wait until we are talked to (or timeout)
                        (self.ws_socket, address) = sock.accept()
                        loginf('Connected to address {0}'.format(address))
                        break
                    except socket.timeout:
                        retry_counter -= 1
                        loginf('accept timeout')
                        if retry_counter == 0:
                            self.ws_socket = None
                            break
                    except socket.error:
                        network_retry_count -= 1
                        if network_retry_count > 0:
                            # Try accessing the network again after a short break
                            sleep(self.retry_wait)
                            break
                        else:
                            # Run out of attempts
                            raise weewx.RetriesExceeded
                    except Exception as e:
                        self.ws_socket = None
                        loginf('Listening error: {0}'.format(e))
                        break
                sock.close()

                # Make sure that we are talking to a weather station
                if self.ws_socket is None:
                    loginf('Going around again')
                    continue

                # Now read the SETUP packet to find the current value units
                retry_counter = self.retry_count
                try:
                    self.ws_socket.send(self.create_cmd_string(argument='SETUP'))
                except socket.error:
                    network_retry_count -= 1
                    if network_retry_count > 0:
                        # Try accessign the network again after a short break
                        sleep(self.retry_wait)
                        continue
                    else:
                        # Run out of attempts
                        raise weewx.RetriesExceeded
                try:
                    rxData = self.ws_socket.recv(1024)
                except:
                    self.ws_socket.close()
                    self.ws_socket = None
                    continue

                # Interpret the data
                interp_data = struct.unpack("8s8s8s8s8s15b", rxData)
                # The fields are:
                #   [0] - The device ID
                #   [1] - The command (WRITE)
                #   [2] - The argument (SETUP)
                #   [3] - some part of the command that is echoed
                #   [4] - some response that overlaps the command and is not yet understood
                #   [5] - Time format (1 = 'H:mm:ss', 2 = 'h:mm:ss AM', 4 = 'AM h:mm:ss')
                #   [6] - Date format (16 = 'DD-MM-YYYY', 32 = 'MM-DD-YYYY', 64 = 'YYYY-MM-DD')
                #   [7] - Temperature unit (0 = Celsius, 1 = Fahrenheit)
                #   [8] - Pressure Unit (0 = hPa, 1 = inHg, 2 = mmHg)
                #   [9] - Wind speed (0=m/s, 1=km/h, 2=knot, 3=mph, 4=bft, 5=ft/s)
                #   [10]- Rainfall unit (0 = mm, 1 = in)
                #   [11]- Solar Radiation (0=lux, 1=fc, 2=W/m^2)
                #   [12]- Rain display (0=rain rate,1=daily, 2-weekly, 3=monthly, 4=yearly)
                #   [13]- Graph Time (0=12h, 1=24h, 2=48h, 3=72h)
                #   [14]- Barometer display (0=Abs, 1=Rel)
                #   [15]- Weather Threshold (number)
                #   [16]- Storm Threshold (number)
                #   [17]- Current Weather (0=Sun, 1=partly cloudy, 2=cloudy, 3=rain, 4=storm threshold)
                #   [18]- Rainfall reset month (1=January...)
                #   [19]- Update interval (number, minutes)
                # We are interested in the temperature, pressure, wind speed, rainfall and solar radiation values
                self.temperature_unit = interp_data[7]
                self.pressure_unit = interp_data[8]
                self.wind_unit = interp_data[9]
                self.rain_unit = interp_data[10]
                self.solar_unit = interp_data[11]
                
                # If we get here then we have established contact
                loginf('Established contact at %s' %
                       datetime.datetime.now().strftime('%d/%m/%y %H:%M:%S'))
            else:
                # Internal test mode
                print('HP1000 - Test Mode - Pretending connection has been made')
                self.temperature_unit = 0  # C
                self.pressure_unit = 0  # hPa
                self.wind_unit = 0  # m/s
                self.rain_unit = 0  # mm
                self.solar_unit = 2  # w/m^2
                self.rainfall_amount = 0
                self.max_iterations = 2 * 3 * 6 * 2 * 3 * 2
                self.iteration_count = 0
                self.ws_socket = 1  # Any old junk will do as we don't reference this in test mode


    def genLoopPackets(self):
        network_retry_count = self.max_retry   # Local network failure retry counter
        while True:
            # Make sure we are connected to the weather station
            # If we can't then this will raise an exception
            self.connectToWeatherStation()
            
            # See if we need to delay requesting the packet
            if self.loop_delay is not None:
                time.sleep( self.loop_delay)
            
            # Get current data
            if not self.internal_test_mode:
                try:
                    self.ws_socket.send(self.create_cmd_string(argument='NOWRECORD'))
                except socket.error:
                    network_retry_count -= 1
                    if network_retry_count > 0:
                        # Try accessing the network again after a short break
                        sleep(self.retry_wait)
                        self.ws_socket.close()
                        self.ws_socket = None
                        continue
                    else:
                        # Run out of attempts
                        raise weewx.RetriesExceeded
                try:
                    rxData = self.ws_socket.recv(1024)
                except:
                    self.ws_socket.close()
                    self.ws_socket = None
                    continue
                interp_data = struct.unpack("8s8s16s8shbb14fbbh", rxData)
            else:
                # Create test mode data
                interp_data = [0] * 25
                # Internal Test Mode
                # interp_data[0] - device ID
                # interp_data[1] - Command
                # interp_data[2] - Argument
                # interp_data[3] - junk (yet to be understood)
                interp_data[4] = 95  # Wind direction in degrees
                interp_data[5] = 49  # Inside humidity in percent
                interp_data[6] = 71  # Outside humidity in percent

                if self.temperature_unit == 0:
                    interp_data[7] = 24.5  # inside temp in C
                    interp_data[10] = 15.9  # outside temp in C
                    interp_data[11] = 7.4  # dewpoint in C
                    interp_data[12] = 15.8  # Windchill in C
                else:
                    interp_data[7] = 24.5 * 9 / 5 + 32  # F
                    interp_data[10] = 15.9 * 9 / 5 + 32
                    interp_data[11] = 7.4 * 9 / 5 + 32
                    interp_data[12] = 15.8 * 9 / 5 + 32

                if self.pressure_unit == 0:
                    interp_data[8] = 1014.3  # Pressure in hPa
                    interp_data[9] = 998.4  # Barometer in hPa
                elif self.pressure_unit == 1:
                    interp_data[8] = 1014.3 * 0.02953  # Pressure in inHg
                    interp_data[9] = 998.4 * 0.02953  # Barometer in inHg
                else:
                    interp_data[8] = 1014.3 * 0.75006156  # Pressure in mmHg
                    interp_data[9] = 998.4 * 0.75006156  # Barometer in mmHg

                if self.wind_unit == 0:
                    interp_data[13] = 1.5  # Wind speed in m/s
                    interp_data[14] = 3.8  # Wind gust in m/s
                elif self.wind_unit == 1:
                    interp_data[13] = 1.5 * 3.6  # Wind speed in km/hr
                    interp_data[14] = 3.8 * 3.6  # Wind gust in km/hr
                elif self.wind_unit == 2:
                    interp_data[13] = 1.5 * 1.94384  # Wind speed in knots
                    interp_data[14] = 3.8 * 1.94384  # Wind gust in knots
                elif self.wind_unit == 3:
                    interp_data[13] = 1.5 * 2.23694  # Wind speed in mph
                    interp_data[14] = 3.8 * 2.23694  # Wind gust in mph
                elif self.wind_unit == 4:
                    # Formula taken from https://en.wikipedia.org/wiki/Beaufort_scale
                    # and inverted for a rough approximation
                    interp_data[13] = int(round(math.pow(1.5 / 0.836, 2.0 / 3.0)))
                    interp_data[14] = int(round(math.pow(3.8 / 0.836, 2.0 / 3.0)))
                else:
                    interp_data[13] = 1.5 * 3.28084  # Wind speed in ft/s
                    interp_data[14] = 3.8 * 3.28084  # Wind gust in fts

                if self.solar_unit == 0:
                    interp_data[20] = 532.7 / 4.02  # Sunlight in Lux
                elif self.solar_unit == 1:
                    interp_data[20] = 532.7 / 0.04358  # Sunlight in fc
                else:
                    interp_data[20] = 532.7  # w/m2

                if self.rain_unit == 0:
                    interp_data[16] = self.rainfall_amount  # Rain in mm
                else:
                    interp_data[16] = self.rainfall_amount / 25.4  # Rain in inches
                self.rainfall_amount += 0.1  # Heavy rain!!! - At least it will register

                interp_data[21] = 3  # Actually the UVI

                print('Temperature Unit: %d' % self.temperature_unit)
                print('   Pressure Unit: %d' % self.pressure_unit)
                print('       Wind Unit: %d' % self.wind_unit)
                print('      Solar Unit: %d' % self.solar_unit)
                print('       Rain Unit: %d' % self.rain_unit)
                # End of loading up the test data
            
            # Build the LOOP packet from the data
            _packet = {'dateTime': int(time.time()), 
                       'usUnits': weewx.METRICWX, 
                       'windDir': None if interp_data[4] == 32767 else interp_data[4],
                       'inHumidity': interp_data[5], 
                       'outHumidity': None if interp_data[6] == 127 else interp_data[6]}

            # For units that are set by the console, convert them to metricwx if necessary
            sourceUnit = ''
            if self.temperature_unit == 0:
                sourceUnit = 'degree_C'
            else:
                sourceUnit = 'degree_F'
            if interp_data[7] == 32767:
                _packet['inTemp'] = None
            else:
                _packet['inTemp'] = self.convert_units((interp_data[7], sourceUnit, 
                                                       'group_temperature'), weewx.METRICWX)[0]
            if interp_data[10] >= 3276:
                _packet['outTemp'] = None
            else:
                _packet['outTemp'] = self.convert_units((interp_data[10], sourceUnit, 
                                                        'group_temperature'), weewx.METRICWX)[0]
            if interp_data[11] >= 3276:
                _packet['dewPoint'] = None
            else:
                _packet['dewPoint'] = self.convert_units((interp_data[11], sourceUnit, 
                                                         'group_temperature'), weewx.METRICWX)[0]
            if interp_data[12] >= 3276:
                _packet['windChill'] = None
            else:
                _packet['windChill'] = self.convert_units((interp_data[12], sourceUnit, 
                                                        'group_temperature'), weewx.METRICWX)[0]

            if self.pressure_unit == 0:
                sourceUnit = 'hPa'
            elif self.pressure_unit == 1:
                sourceUnit = 'inHg'
            else:
                sourceUnit = 'mmHg'
            if interp_data[8] >= 3276:
                _packet['pressure'] = None
            else:
                _packet['pressure'] = self.convert_units((interp_data[8], sourceUnit, 
                                                         'group_pressure'), weewx.METRICWX)[0]
            if interp_data[9] >= 3276:
                _packet['pressure'] = None
            else:
                _packet['barometer'] = self.convert_units((interp_data[9], sourceUnit,
                                                          'group_pressure'), weewx.METRICWX)[0]

            if self.wind_unit == 0:
                sourceUnit = 'meter_per_second'
            elif self.wind_unit == 1:
                sourceUnit = 'km_per_hour'
            elif self.wind_unit == 2:
                sourceUnit = 'knot'
            elif self.wind_unit == 3:
                sourceUnit = 'mile_per_hour'
            elif self.wind_unit == 4:
                loginf('Beaufort Wind Scale Used - Using Approximation')
                interp_data = list(interp_data) # Convert to a list so we can alter the values
                sourceUnit = 'meter_per_second'  # Used so there will be no scale factor applied
                # Formula taken from https://en.wikipedia.org/wiki/Beaufort_scale
                interp_data[13] = 0.836 * math.pow(interp_data[13], 1.5)
                interp_data[14] = 0.836 * math.pow(interp_data[14], 1.5)
            else:
                sourceUnit = 'meter_per_second'  # Used so no scale factor will be applied
                interp_data = list(interp_data) # Convert to a list so we can alter the values
                interp_data[13] *= 0.3048  # ft/s to m/s
                interp_data[14] *= 0.3048
            if interp_data[13] >= 3276:
                _packet['windSpeed'] = None
            else:
                _packet['windSpeed'] = self.convert_units((interp_data[13], sourceUnit, 
                                                          'group_speed'), weewx.METRICWX)[0]
            if interp_data[14] >= 3276:
                _packet['windGust'] = None
            else:
                _packet['windGust'] = self.convert_units((interp_data[14], sourceUnit, 
                                                         'group_speed'), weewx.METRICWX)[0]

            # Weewx does not have a standard for Lux of foot-candles
            if interp_data[20] > 2147480:
                _packet['radiation'] = None
            elif self.solar_unit == 0:
                _packet['radiation'] = interp_data[20] * 4.02  # Lux to w/m2 for sunlight
            elif self.solar_unit == 1:
                _packet['radiation'] = interp_data[20] * 0.04358  # fc to photons *0.199) to w/m2 (0.219)
            else:
                _packet['radiation'] = interp_data[20]
            if interp_data[21] < 0:
                _packet['UV'] = None
            else:
                _packet['UV'] = interp_data[21]  # Actually the UVI

            current_time = datetime.datetime.now()
            if self.last_rain_value is None:
                # Should be the first time through
                _packet['rain'] = None
            else:
                # Regular path
                if interp_data[16] >= 214748367:
                    _packet['rain'] = None
                elif current_time.time() > self.last_rain_time.time() and \
                                interp_data[16] >= self.last_rain_value:
                    # Still in the same day as the previous loop and
                    # the rain value is not lower now than the last reading
                    if self.rain_unit == 0:
                        _packet['rain'] = interp_data[16] - self.last_rain_value
                    else:
                        _packet['rain'] = (interp_data[16] - self.last_rain_value) * 25.4  # in to mm
                else:
                    # We have started a new day or the rain value has (somehow) gone down
                    # without a 'new day reset' in the weather station
                    _packet['rain'] = 0.0
            self.last_rain_value = interp_data[16]
            self.last_rain_time = current_time
            # Leave 'rainRate' to be calculated by wxservice

            if self.internal_test_mode:
                # Increment the various units, wrapping around as necessary
                self.temperature_unit += 1
                if self.temperature_unit > 1:
                    self.temperature_unit = 0
                self.pressure_unit += 1
                if self.pressure_unit > 2:
                    self.pressure_unit = 0
                self.wind_unit += 1
                if self.wind_unit > 5:
                    self.wind_unit = 0
                self.solar_unit += 1
                if self.solar_unit > 2:
                    self.solar_unit = 0
                self.rain_unit += 1
                if self.rain_unit > 1:
                    self.rain_unit = 0

                self.iteration_count += 1
                if self.iteration_count > self.max_iterations:
                    sys.exit()

            yield _packet

    @property
    def hardware_name(self):
        return self.ws_name

    def internal_testing(self, new_state=False):
        self.internal_test_mode = new_state
        
    def getHistoryData( self, year, record_count, starting_record):
        try:
            # Build the command packet
            cmd_packet = struct.pack('8s8s16s2i2hi',
                'PC2000', 'READ', 'HISTORY_DATA',
                48, record_count * 60 + 40,
                year, record_count, starting_record)
            self.ws_socket.send(cmd_packet)
            rx_data = self.ws_socket.recv(8192)
        except Exception as e:
            loginf(str(e))
            raise weewx.RetriesExceeded
            
        # Get the length of the full returned packet
        pkt_length = struct.unpack('I', rx_data[32:36])[0]
        while len(rx_data) < pkt_length:
            # the full packet is being send in small chunks
            rx_data += self.ws_socket.recv(8192)
        return rx_data

    def genStartupRecords(self, lastTimestamp):
        #Start by making sure we can access the weather station
        #If we can't then the function will raise an exception
        self.connectToWeatherStation()
        loginf("Retrieving startup records")
        
        while True:            
            # Find out what data is available from the weather station
            try:
                cmd_packet = struct.pack('8s8s16s2i',
                    'PC2000', 'READ', 'HISTORY_FILE',
                    40, 0)
                self.ws_socket.send(cmd_packet)
                rxData = self.ws_socket.recv(1024)
            except:
#                loginf("Error #1")
                raise weewx.RetriesExceeded
            interp_data = struct.unpack('8s8s16s4h8H8I', rxData)
        
            # Look to see if we have data for the year we are interested in
            year_index = None
            epoch = datetime.datetime(1601,1,1)
            if lastTimestamp is None:
                # Special case - we are starting from an empty database
                # Therefore find the first year with data (i.e. the 'year' is not 0)
                year_index = [x for x, y in enumerate(interp_data[7:15],7) if y != 0][-1]
                start_record = 0
                last_rain_value = 0
                last_record_date = None
            else:
                start_date = datetime.datetime.fromtimestamp(lastTimestamp)
                last_record_date = start_date
                for index, ws_year in \
                            reversed(list(enumerate(interp_data[7:15],7))):
                    if ws_year >= start_date.year:
                        # We have data for the required year
                        # Find the date of the first record for this year
                        year_index = index
                        break;
                if year_index is None:
                    # The weather station does not have the requested start year
                    # and all of the data is older - there is nothing we can add
#                    loginf("No more to retrieve")
                    return
            
                # Find the record number of the first record with a date after
                # the start_date using a binary search
                year = interp_data[year_index]
                lower = 0
                upper = interp_data[year_index + 8] - 1  # max index for records held for that year

                while True:
                    if lower == upper:
                        # the lower and upper indicies are the same
                        sample = upper
                        break
                    sample = (upper + lower) // 2
                    # Read the data with the 'sample' record number
                    # This might be a slow way as it takes time for the 
                    # weather station to respond. The alternative is to read
                    # multiple records at a time but in the early stages of the binary
                    # search, the records are a long way apart so there is little gain
                    rec_data = self.getHistoryData( year, 1, sample)
                
                    # Extract the timestamp from the first 4 words
                    # The value is 100nSec since 1/1/1601!!!!
                    record_datetime = struct.unpack('Q', rec_data[40:48])[0] / 10 #uSec
                    record_datetime = epoch + \
                            datetime.timedelta(microseconds=record_datetime)

                    # While we have the data, also record the records daily rain
                    last_rain_value = struct.unpack('i', rec_data[76:80])[0] / 10.0
                
                    if start_date == record_datetime:
                        # The values are the same - return sample index + 1
                        sample += 1
                        break
                    if start_date > record_datetime:
                        if lower == sample:
                            sample += 1     # Go for the next entry
                            break
                        lower = sample + 1
                    else:
                        if upper == sample:
                            break
                        upper = sample
                start_record = sample

            # Sample will be the record number of the first record with the 
            # *NEXT* record to pass back.
            # Exception - if the target date is later than the last record
            # then we are pointed to that last record index
            
            # Check to see if the sample record date is the last history record
            # If it is then there is no point in continuing as we have everything
            if year_index == 7 and start_record == interp_data[year_index + 8] - 1:
                break;

            # Read all records from here to the last record the weather startion has
            # We need to account for crossing year boundaries
            while year_index >= 7:
                year = interp_data[year_index]
                year_record_count = interp_data[year_index + 8]
                record_count = 100
                if record_count + start_record >= year_record_count:
                    record_count = year_record_count - start_record - 1
#                loginf("Retrieving {0} records in year {1} from {2}".format(
#                            record_count, year, start_record))
                if record_count > 0:
                    rec_packet = self.getHistoryData(year, record_count, start_record)
                    rec_index = 40      # Skip the header data
                    base = start_record
                    start_record += record_count
                    while record_count > 0:
                        rec_data = struct.unpack('Q12h7I', 
                                        rec_packet[rec_index:rec_index + 60])
                        # Note: the values in the HISTORY_DATA record always seem to be
                        # metric, regardless of the setup options
                        # Please let me know if this is NOT THE CASE
                        _packet = {'usUnits': weewx.METRICWX}
                        rec_data = list(rec_data)

                        record_datetime = epoch + \
                                datetime.timedelta(microseconds=rec_data[0] / 10.0)
                        _packet['dateTime'] = time.mktime(record_datetime.timetuple())
                        _packet['inTemp'] = None if rec_data[1] == 32767 else rec_data[1] / 10.0
                        _packet['inHumidity'] = None if rec_data[2] == 32767 else rec_data[2]
                        _packet['pressure'] = None if rec_data[3] == 32767 else rec_data[3] / 10.0
                        _packet['barometer'] = None if rec_data[4] == 32767 else rec_data[4] / 10.0
                        _packet['outTemp'] = None if rec_data[5] == 32767 else rec_data[5] / 10.0
                        _packet['outHumidity'] = None if rec_data[6] == 127 else rec_data[6]
                        _packet['dewPoint'] = None if rec_data[7] == 32767 else rec_data[7] / 10.0
                        _packet['windchill'] = None if rec_data[8] == 32767 else rec_data[8] / 10.0
                        # rec_data[9] / 10.0 might be 'heatIndex'
                        _packet['windSpeed'] = None if rec_data[10] == 32767 else rec_data[10] / 10.0
                        _packet['windGust'] = None if rec_data[11] == 32767 else rec_data[11] / 10.0
                        _packet['windDir'] = None if rec_data[12] == 32767 else rec_data[12]
                        # rec_data[13] is the 'rain rate'

                        # Calculate the 'delta rain' since the last record
                        # Reset on change of day
                        rain = None if rec_data[14] == 2147483647 else rec_data[14] / 10.0
                        if last_record_date is None or rain is None or last_rain_value is None:
                            _packet['rain'] = None
                        elif last_record_date.time() > record_datetime.time() or \
                                   last_rain_value > rain:
                            # start of a new day (or other cause for the rain to be lower than before)
                            _packet['rain'] = 0.0
                        else:
                            _packet['rain'] = rain - last_rain_value
                        last_rain_value = rain
                    
                        #rec_data[15] is the 'weekly rain' total
                        #rec_data[16] is the 'monthly rain' total
                        #rec_data[17] is the 'yearly rain' total
                    
                        _packet['UV'] = None if rec_data[18] == 32767 else int(round(rec_data[18] / 250))   # Convert uW/cm2 to UVI
                        _packet['radiation'] = None if rec_data[19] == 2147483647 else rec_data[19] / 1267.0    # 126.7 lux/(w/m^2)
                        _packet['interval'] = 5
                
                        yield _packet
                
                        # Set up for the next record
                        record_count -= 1
                        rec_index += 60
                        last_record_date = record_datetime
        
                # reached the end of this packet
                if start_record >= year_record_count - 1:
                    # Reached the end of the year
                    year_index -= 1
                    start_record = 0

            # Go around again and pick up the history records
            # that have been added since we started
            lastTimestamp = time.mktime(record_datetime.timetuple())
                
                
                
def confeditor_loader():
    return HP1000ConfEditor()


class HP1000ConfEditor(weewx.drivers.AbstractConfEditor):
    @property
    def default_stanza(self):
        return """
[HP1000]
    # This section is for the weewx HP1000 weather station driver

    # The IP address mask to search for a weather station
    # Define this if you DO NOT have the 'netifaces' Python
    # package installed on your computer or you want to 
    # force the driver to use a specific broadcase address
    #ip_address_mask = "10.1.1.255"
    
    # The retry count for getting a response from the weather station
    retry_count = 5
    
    # Socket timeout value (seconds)
    socket_timeout = 5
    
    # Loop delay time (seconds)
    # None or not specified means loop packets are generated as fast as possible
    # (approx every few seconds) and will increase network traffic volume
    loop_delay = 15
    
    # Number of times to try to access the network
    max_retry = 3
    
    # Number of seconds to wait between attempts to access the network
    retry_wait = 5

    # The driver to use:
    driver = user.HP1000
"""


if __name__ == "__main__":
    station = HP1000Driver(retry_count="5", 
                           socket_timeout="5", loop_delay="2")
    station.internal_testing(True)
    print('All of the following should return (approx.) the same values')
    for packet in station.genLoopPackets():
        pass

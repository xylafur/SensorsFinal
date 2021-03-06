"""
    Lidar Packet Info:
        This data protocol is used by "lidar4_main_code" firmware. Single data packet consists of parts:

            Header: [0xAA, 0xBB, 0xCC, 0xDD] - 4 bytes.
            Status: [LSB + MSB] - (16-bit value) - 2 bytes.
            Duration of the last turn: [LSB + MSB] - (16-bit value is ms) - 2 bytes.
            Distance data: [(LSB + MSB)*360] - (360 x 16-bit values) - 720 bytes.

        Total number of bytes in this packet - 728.

        Every "distance data value" is a 16-bit unsigned value, corresponding to a certain rotation
        angle. In fact "distance data value" is a position of the laser light spot at the TSL1401.
        High level software must convert that values to a real distance values.
"""

###############################################################################
#   Shared variables and such.  These are used by both threads
###############################################################################
import queue
import serial

data_queue = queue.Queue()

running = True
EXPECTED_PACKET_LENGTH = 728

def get_data_from_buffer():
    """
        - Gets the next data packet from the buffer
        - Removes it from the buffer
        - Returns the packet as a bytes object
    """
    # TODO: Real functionality needs to be implemented
    return data_queue.get()


###############################################################################
#   Functions to read from LIDAR
###############################################################################
# I think this has something to do with the resolution of the sensor or soemthing..... no
# documentation in his C# code, so I'll have to go look it up
LIDAR_MAGIC = 16383
LIDAR_COEF_A = 3.67E-05
LIDAR_COEF_B = 0.417
BASE_LENGTH = 5.8


# This is directly from his ConvertToLength function in Form1.cs
# NOTE: In his function he makes BASE_LENGTH negathie.. I could not figure out why so I removed
#       this
convert_lidar_point_to_length = lambda point:   \
    (BASE_LENGTH / math.tan((point&LIDAR_MAGIC) * LIDAR_COEF_A - LIDAR_COEFF_B)) / 100.0 \
    if point&LIDAR_MAGIC > 50 else 0

def convert_distance_to_lidar_point(distance_m):
    """
        This is just the oposite of convert_lidar_point_to_length.
        This is used for generating mock data
        This function also injects some noise
    """
    if not distance_m:
        return distance_m
    value_no_noise = (math.atan(BASE_LENGTH / (distance_m * 100)) + LIDAR_COEF_B) / LIDAR_COEF_A
    noise = random.randint(0, 500) << len(bin(LIDAR_MAGIC)[2:])
    return int(value_no_noise) | noise


import math
import random


"""
    LabView Packet Format
        

    NOTE:
        I originally thought that we could transmit the data already converted to x y coordinates,
        but that coule involve 
"""

class FakeLidar:
    """
        This class is meant to mimic the LIDAR that we will be intefacing with over serial.
    """
    def __init__(self, device, baud, timeout):
        self.device = device
        self.baud = baud 
        self.timeout = timeout 

        self.current_reading = 0

    def generate_circle(self, radius=5, rotation_period_ms=500):
        """ Generates a circle of radius 'radius' in polar format.
            Encodes the distance data in a format that would be expected from the LIDAR
        """
        #TODO: Check endianness
        header = [0xAA, 0xBB, 0xCC, 0xDD]
        # I don't think that the status flags are used for anything..
        status = [0x00, 0x00]
        rotation = [rotation_period_ms & 0xFF, (rotation_period_ms & 0xFF00)>>8]
        distances = []
        for dist in range(360):
            # Each lindar data point is 2 bytes
            dist = convert_distance_to_lidar_point(radius)
            distances.append(dist & 0xFF)
            distances.append((dist & 0xFF00)>>8)

        return bytes(header + status + rotation + distances)

    def read(self, *args):
        self.current_reading += 1
        return self.generate_circle()

    def close(self):
        print("Closing mock lidar!")

def generate_mock_lidar_data(device):
    return device.read()
 
def read_data_from_uart(device, _bytes=EXPECTED_PACKET_LENGTH):
    """
        - In linux the terminal driver will buffer input even if the device it is not opened
            - this means we should just be able to read from where we last read in linux
    """
    data = device.read(_bytes)
    return data

def get_data(device, mock=False):
    return generate_mock_lidar_data(device) if mock else read_data_from_uart(device)

def queue_data(data):
    data_queue.put(data)

def get_serial_device(device, baud, timeout, mock):
    """
        set up and open the given serial device so that it is read to be used
    """
    if mock:
        return FakeLidar(device, baud, timeout=timeout)
    return serial.Serial(device, baud, timeout=timeout)

def close_device(device):
    device.close()

def remove_header(lidar_data):
    """    first 4 bytes are header data [aa, bb, cc, dd]
    """
    return lidar_data[4:]

def remove_status(lidar_data):
    """    bytes 5 and 6 are status data, we check if the header is removed first
    """
    if all([[b'aa', b'bb', b'cc', b'dd'][ii] == lidar_data[ii] for ii in range(3)]):
        # The header is still there, we remove the header too
        return lidar_data[6:]
    return lidar_data[2:]

def remove_rotation(lidar_data):
    """    bytes 5 and 6 are status data, we check if the header is removed first
    """
    if all([[b'aa', b'bb', b'cc', b'dd'][ii] == lidar_data[ii] for ii in range(3)]):
        # The header is still there, we remove the header too
        return lidar_data[8:]
    return lidar_data[2:]

def swap_endianness(lidar_data):
    """    each word is 2 bytes long.. so this swap function is specific to this system
    """
    out = []
    for ii in range(0, len(lidar_data), 2):
        out.append(lidar_data[ii+1])
        out.append(lidar_data[ii])
    return bytes(out)

def convert_to_byte_string(b):
    l = []
    sl = [hex(b[ii])[2:].rjust(2, '0') for ii in range(len(b))]
    for e in sl:
        for c in e:
            l.append(c)
    return bytes([ord(c) for c in l])

import string
def lidar_main(args):
    # Eventually I think we will have to add windows support
    device = get_serial_device(args.device, args.baud, args.serial_timeout, args.mock)
    try:
        # Just continually read from UART and move data to our buffer
        while running:
            lidar_data = get_data(device, mock=args.mock)
            if len(lidar_data) < EXPECTED_PACKET_LENGTH:
                print("Packet from lidar is too small!  Only got {} bytes".format(len(lidar_data)))
                print(" Data: {}".format(lidar_data))
                continue

            lidar_data = remove_header(lidar_data)
            lidar_data = remove_status(lidar_data)
            lidar_data = remove_rotation(lidar_data)
            
            lidar_data = swap_endianness(lidar_data)
            lidar_data = convert_to_byte_string(lidar_data)
            queue_data(lidar_data)
            #queue_data(bytes([ord(c) for c in list(string.ascii_lowercase)]))
    finally:
        close_device(device)


###############################################################################
#   Functions to send info to client over TCP
###############################################################################
import socket

def socket_main(args):
    address = args.address
    port = args.port
    buffer_size = args.buffer_size

    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind((address, port))

    if args.debug:
        print("Created server at {}:{}".format(address, port))

    s.listen(1)
    s.settimeout(args.socket_timeout)

    while running:
        # Accept a connection from a client
        try:
            conn, client_address = s.accept()
        except socket.timeout:
            continue

        try:
            # TODO: Make sure that all data is actually sent
            to_send = get_data_from_buffer()

            if args.debug:
                print("Sending {} bytes {!r}".format(len(to_send), to_send))

            conn.sendall(to_send)

        finally:
            conn.close()


###############################################################################
#   Main function and argument parsing
###############################################################################
from threading import Thread
import argparse

parser = argparse.ArgumentParser(
        description="Program to read from LIDAR attached over UART and transmit to LabView over TCP")

parser.add_argument("-a", "--address", default="localhost", type=str)
parser.add_argument("-p", "--port", default=5005, type=int)
parser.add_argument("-b", "--buffer_size", default=728, type=int)
parser.add_argument("-s", "--device", default="/dev/ttyUSB0", type=str)
parser.add_argument("-d", "--debug", action="store_true", default=False)
parser.add_argument("-m", "--mock", action="store_true", default=False)
parser.add_argument("-t", "--socket_timeout", type=float, default=1)

parser.add_argument("-r", "--serial_timeout", type=float, default=1)
parser.add_argument("-u", "--baud", type=int, default=115200)

def main():
    global running

    args = parser.parse_args()
    # Start get data in a thread
    # Start ther server in a thread
    lidar_thread = Thread(target=lidar_main, args=(args,))
    tcp_thread = Thread(target=socket_main, args=(args,))

    if args.debug:
        print("Starting LIDAR and TCP threads")

    try:
        lidar_thread.start()
        tcp_thread.start()
        while 1:
            pass
    except KeyboardInterrupt:
        print("User issues Ctrl^C! Stopping program")
    finally:
        running = False

        lidar_thread.join()
        tcp_thread.join()

    if args.debug:
        print("End of Program, thread status:")
        print("   LIDAR: {}".format(lidar_thread.is_alive()))
        print("   TCP:   {}".format(tcp_thread.is_alive()))


if __name__ == '__main__':
    main()

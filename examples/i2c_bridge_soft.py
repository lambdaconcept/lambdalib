# 2023 - LambdaConcept - po@lambdaconcept.com

import time
import serial

from lambdalib.software.i2c.bus import *
from lambdalib.software.usb.device import *


def main():
    dev = serial.Serial("/dev/ttyUSB2", baudrate=3e6)
    dev.reset_input_buffer()

    # usb = USBDevice(512, vid=0xffff, pid=0x1234)
    # dev = usb.get_endpoint(1)

    bus = I2CBus(dev, reg_addr_width=16)
    bus.discover()

    addr = 0x29
    length = 20
    data = bus.read_block_data(addr, 0x00, length)

    print("read:", data)


if __name__ == "__main__":
    main()

# 2023 - LambdaConcept - po@lambdaconcept.com

import sys
import time

from lambdalib.software.utils import *
from lambdalib.software.usb.device import *


def master(dev):
    wdata = [i % 256 for i in range(3*512)]
    print("wr:", wdata)
    rdata = dev.exchange(wdata)
    print("rd:", rdata)

def slave(dev):
    while True:
        rdata = dev.recv()
        hexdump(rdata)

def main(mode):
    pid = 0x1234 if mode == "master" else 0x1235
    usb = USBDevice(512, vid=0xffff, pid=pid)
    dev = usb.get_endpoint(1)

    if mode == "master":
        master(dev)
    elif mode == "slave":
        slave(dev)

if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in ["master", "slave"]:
        print("usage: {} master|slave".format(sys.argv[0]))
        sys.exit(1)
    mode = sys.argv[1]
    main(mode)

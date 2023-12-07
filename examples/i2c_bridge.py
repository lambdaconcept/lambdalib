# 2023 - LambdaConcept - po@lambdaconcept.com

import logging

from amaranth import *

from lambdalib.cores.i2c.proto import *
from lambdalib.cores.usb.generic_device import *
from lambdalib.cores.serial import *
from lambdalib.interface import stream

from crg import *

from amaranth.build import *


class Top(Elaboratable):
    def __init__(self, sys_clk_freq, has_ulpi=True, bridge_type=None):
        self.sys_clk_freq = sys_clk_freq
        self.has_ulpi = has_ulpi
        self.bridge_type = bridge_type

    def elaborate(self, platform):
        m = Module()

        # CRG
        m.submodules.crg = CRG_LatticeECP5(self.sys_clk_freq, has_ulpi=self.has_ulpi)

        if self.bridge_type == "uart":

            # Create the UART device
            baudrate = 3e6
            m.submodules.link = link = AsyncSerialStream(
                divisor=int(self.sys_clk_freq / baudrate),
                pins=platform.request("uart", 0),
            )

        elif self.bridge_type == "usb":

            # Create the USB device
            usb_pins = platform.request("ulpi" if self.has_ulpi else "usb")
            m.submodules.link = link = USBGenericDevice(pins=usb_pins,
                                                        vid=0xffff, pid=0x1234)

        # Create the I2C device
        pin = platform.request("i2c")
        m.submodules.i2c = i2c = I2CProto(self.sys_clk_freq,
                                          i2c_pins=pin, i2c_freq=400e3)

        # FIFO buffer
        m.submodules.fifo_rx = fifo_rx = stream.SyncFIFO(link.source.description, 32)
        m.submodules.fifo_tx = fifo_tx = stream.SyncFIFO(link.sink.description, 32)

        m.d.comb += [
            link.source.connect(fifo_rx.sink),
            fifo_rx.source.connect(i2c.sink),
            i2c.source.connect(fifo_tx.sink),
            fifo_tx.source.connect(link.sink),
        ]

        # Output to LED
        max_led = 0
        for i in range(4):
            if ("rgb_led", i) in platform.resources:
                max_led += 1
        leds = [platform.request('rgb_led', i) for i in range(max_led)]
        m.d.comb += [
            leds[0].r.eq(link.source.valid & link.source.ready),
            leds[1].r.eq(link.sink.valid & link.sink.ready),
        ]

        return m


def build_ecpix(top):
    from amaranth_boards.ecpix5 import ECPIX585Platform
    platform = ECPIX585Platform()
    platform.add_resources([
        Resource("i2c", 0,
            Subsignal("scl", Pins("1", dir="o",  conn=("pmod", 0))),
            Subsignal("sda", Pins("2", dir="io", conn=("pmod", 0))),
            Attrs(IO_TYPE="LVCMOS33", PULLMODE="UP"),
        ),
    ])

    platform.build(top, name="top", build_dir="build.ecpix.i2c_bridge",
                   do_program=False, verbose=False,
                   ecppack_opts="--compress --freq 62.0") # --spimode qspi")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--platform", choices=("ecpix"),
                        default="ecpix",
                        help="platform variant (default: %(default)s)")
    parser.add_argument("--type", choices=("usb", "uart"),
                        default="uart",
                        help="bridge type (default: %(default)s)")

    args = parser.parse_args()

    if args.platform == "ecpix":
        top = Top(100e6, has_ulpi=True, bridge_type=args.type)
        build_ecpix(top)

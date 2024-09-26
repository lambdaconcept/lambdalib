# 2023 - LambdaConcept - po@lambdaconcept.com

import logging

from amaranth import *

from lambdalib.cores.spi.master import *
from lambdalib.cores.spi.slave import *
from lambdalib.cores.spi.stream import *
from lambdalib.cores.usb.generic_device import *
from lambdalib.interface import stream

from crg import *

from amaranth.build import *


class SPIMasterBridge(Elaboratable):
    """ Bridge a USB endpoint to a SPI master.

    This can be used to act as a SPI master from the PC.
    """
    def __init__(self, sys_clk_freq, spi_freq=24e6, spi_width=1, has_ulpi=True):
        self.sys_clk_freq = sys_clk_freq
        self.spi_freq = spi_freq
        self.spi_width = spi_width
        self.has_ulpi = has_ulpi

    def elaborate(self, platform):
        m = Module()

        # CRG
        m.submodules.crg = CRG_LatticeECP5(self.sys_clk_freq, has_ulpi=self.has_ulpi)

        # Create the USB device
        usb_pins = platform.request("ulpi" if self.has_ulpi else "usb")
        m.submodules.link = link = USBGenericDevice(pins=usb_pins,
                                                    vid=0xffff, pid=0x1234)

        # Create the SPI PHY.
        spi_pins = platform.request("spi", 0 if self.spi_width == 1 else 1)
        m.submodules.spi_phy = spi_phy = SPIPHYMaster(
            spi_pins, self.sys_clk_freq,
            spi_clk_freq=self.spi_freq,
        )

        # Create the USB-SPI bridge
        m.submodules.api = api = SPIStream(bus_width=self.spi_width)

        m.d.comb += [
            spi_phy.cs.eq(api.cs),

            link.source.connect(api.data_sink),
            api.phy_source.connect(spi_phy.sink),
            spi_phy.source.connect(api.phy_sink),
            api.data_source.connect(link.sink),
        ]

        # Output to LED
        max_led = 0
        for i in range(4):
            if ("rgb_led", i) in platform.resources:
                max_led += 1
        leds = [platform.request('rgb_led', i) for i in range(max_led)]
        m.d.comb += [
            leds[0].r.o.eq(link.rx_activity),
            leds[1].r.o.eq(link.tx_activity),
        ]

        return m


class SPISlaveBridge(Elaboratable):
    """ Bridge a USB endpoint to a SPI slave.

    (Read only for now, slave cannot send data.)
    """
    def __init__(self, sys_clk_freq, spi_width=1, has_ulpi=True):
        self.sys_clk_freq = sys_clk_freq
        self.spi_width = spi_width
        self.has_ulpi = has_ulpi

    def elaborate(self, platform):
        m = Module()

        # CRG
        m.submodules.crg = CRG_LatticeECP5(self.sys_clk_freq, has_ulpi=self.has_ulpi)

        # Create the USB device
        usb_pins = platform.request("ulpi" if self.has_ulpi else "usb")
        m.submodules.link = link = USBGenericDevice(pins=usb_pins,
                                                    vid=0xffff, pid=0x1235)

        # Create the SPI PHY.
        spi_pins = platform.request("spi", 0 if self.spi_width == 1 else 1)
        m.submodules.spi_phy = spi_phy = SPIPHYSlave(
            spi_pins, width=8, with_len=False,
        )

        m.d.comb += [
            spi_phy.source.connect(link.sink),
            link.source.connect(spi_phy.sink),
        ]

        # Output to LED
        max_led = 0
        for i in range(4):
            if ("rgb_led", i) in platform.resources:
                max_led += 1
        leds = [platform.request('rgb_led', i) for i in range(max_led)]
        m.d.comb += [
            leds[0].r.o.eq(link.rx_activity),
            leds[1].r.o.eq(link.tx_activity),
        ]

        return m


def build_ecpix_master(top):
    from amaranth_boards.ecpix5 import ECPIX585Platform
    platform = ECPIX585Platform()
    platform.add_resources([
        Resource("spi", 0,
            Subsignal("mosi", Pins("1", dir="o", conn=("pmod", 0))),
            Subsignal("miso", Pins("2", dir="i", conn=("pmod", 0))),
            Subsignal("cs_n", Pins("7", dir="o", conn=("pmod", 0))),
            Subsignal("clk",  Pins("8", dir="o", conn=("pmod", 0))),
            Attrs(IO_TYPE="LVCMOS33"),
        ),
        Resource("spi", 1,
            Subsignal("dq",   Pins("1 2 3 4", dir="io", conn=("pmod", 0))),
            Subsignal("cs_n", Pins("7", dir="o", conn=("pmod", 0))),
            Subsignal("clk",  Pins("8", dir="o", conn=("pmod", 0))),
            Attrs(IO_TYPE="LVCMOS33"),
        ),
    ])
    platform.build(top, name="top",
                   build_dir=f"build.ecpix.spi_bridge_x{top.spi_width}.master",
                   do_program=False, verbose=False,
                   ecppack_opts="--compress --freq 62.0") # --spimode qspi")

def build_ecpix_slave(top):
    from amaranth_boards.ecpix5 import ECPIX585Platform
    platform = ECPIX585Platform()
    platform.add_resources([
        Resource("spi", 0,
            Subsignal("mosi", Pins("1", dir="i", conn=("pmod", 0))),
            Subsignal("miso", Pins("2", dir="o", conn=("pmod", 0))),
            Subsignal("cs_n", Pins("7", dir="i", conn=("pmod", 0))),
            Subsignal("clk",  Pins("8", dir="i", conn=("pmod", 0))),
            Attrs(IO_TYPE="LVCMOS33"),
        ),
        Resource("spi", 1,
            Subsignal("dq",   Pins("1 2 3 4", dir="io", conn=("pmod", 0))),
            Subsignal("cs_n", Pins("7", dir="i", conn=("pmod", 0))),
            Subsignal("clk",  Pins("8", dir="i", conn=("pmod", 0))),
            Attrs(IO_TYPE="LVCMOS33"),
        ),
    ])
    platform.build(top, name="top",
                   build_dir=f"build.ecpix.spi_bridge_x{top.spi_width}.slave",
                   do_program=False, verbose=False,
                   ecppack_opts="--compress --freq 62.0") # --spimode qspi")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--platform", choices=(["ecpix"]),
                        default="ecpix",
                        help="platform variant (default: %(default)s)")
    parser.add_argument("--width", choices=("1", "2", "4", "8"),
                        default="1",
                        help="spi bus width (default: %(default)s)")

    args = parser.parse_args()

    if args.platform == "ecpix":
        master = SPIMasterBridge(100e6, spi_freq=25e6, spi_width=int(args.width),
                                 has_ulpi=True)
        build_ecpix_master(master)

        slave = SPISlaveBridge(100e6, spi_width=int(args.width),
                               has_ulpi=True)
        build_ecpix_slave(slave)

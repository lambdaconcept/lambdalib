# 2024 - LambdaConcept - po@lambdaconcept.com

import sys
import logging

from amaranth import *
from amaranth.build import *

from lambdalib.interface import stream
from crg import *

sys.path.append("../gowin-mipi-edp/gateware")
from sn65dsi86 import *

class Top(Elaboratable):
    def __init__(self, sys_clk_freq):
        self.sys_clk_freq = sys_clk_freq

    def elaborate(self, platform):
        m = Module()

        # CRG
        m.submodules.crg = CRG_LatticeECP5(self.sys_clk_freq)

        # Create the I2C device
        pin = platform.request("i2c")
        m.submodules.i2c_init = SN65DSI86Init(self.sys_clk_freq, i2c_pins=pin)

        # Output to LED
        max_led = 0
        for i in range(4):
            if ("rgb_led", i) in platform.resources:
                max_led += 1
        leds = [platform.request('rgb_led', i) for i in range(max_led)]
        m.d.comb += [
            # leds[0].r.eq(link.source.valid & link.source.ready),
            # leds[1].r.eq(link.sink.valid & link.sink.ready),
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

    platform.build(top, name="top", build_dir="build.ecpix.i2c_reginit",
                   do_program=False, verbose=False, do_build=True,
                   ecppack_opts="--compress --freq 62.0") # --spimode qspi")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--platform", choices=("ecpix"),
                        default="ecpix",
                        help="platform variant (default: %(default)s)")

    args = parser.parse_args()

    if args.platform == "ecpix":
        top = Top(100e6)
        build_ecpix(top)

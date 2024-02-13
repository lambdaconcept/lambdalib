# 2023 - LambdaConcept - po@lambdaconcept.com

from amaranth import *
from amaranth.hdl.rec import *


def spi_core2phy_layout(width, with_len=True):
    layout = [
        ("data",  width),
        ("width", range(8 + 1)),    # Supports up to octo spi
        ("oe",    1),
    ]
    if with_len:
        layout += [("len", range(width + 1))]
    return layout

def spi_phy2core_layout(width, with_len=False):
    layout = [
        ("data",  width),
    ]
    if with_len:
        layout += [("len", range(width + 1))]
    return layout

def spi_slave_layout(width, with_len=True):
    layout = [("data", width)]
    if with_len:
        layout += [("len", range(width + 1))]
    return layout

class SPIPinsStub(Record):
    def __init__(self, bus_width=1):
        if bus_width == 1:
            super().__init__([
                ("clk",  1),
                ("cs_n", 1),
                ("miso", 1),
                ("mosi", 1),
            ], name="spi_pins")
        else:
            super().__init__([
                ("clk",  1),
                ("cs_n", 1),
                ("dq", [
                    ("i", bus_width),
                    ("o", bus_width),
                    ("oe", 1),
                ]),
            ], name="spi_pins")

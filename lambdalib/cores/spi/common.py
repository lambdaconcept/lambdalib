# 2023 - LambdaConcept - po@lambdaconcept.com

from amaranth import *
from amaranth.hdl.rec import *


spi_core2phy_layout = [
    ("data", 32), # XXX make this a parameter
    ("len",   6),
    ("width", 4),
    ("mask",  8), # XXX oe always len 1
]

spi_phy2core_layout = [
    ("data", 32),
]

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

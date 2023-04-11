# 2023 - LambdaConcept - po@lambdaconcept.com

from amaranth import *


spi_core2phy_layout = [
    ("data", 32),
    ("len",   6),
    ("width", 4),
    ("mask",  8),
]

spi_phy2core_layout = [
    ("data", 32),
]

def spi_slave_layout(width):
    return [
        ("data", width),
        ("len", range(width + 1)),
    ]

class SPIPinsStub(Record):
    def __init__(self):
        super().__init__([
            ("clk",  1),
            ("cs_n", 1),
            ("miso", 1),
            ("mosi", 1),
        ], name="spi_pins")

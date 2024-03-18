# 2024 - LambdaConcept - po@lambdaconcept.com

from amaranth import *

from ...interface import stream
from .stream import *
from ..mem.stream import *


class I2CRegisterInit(Elaboratable):
    def __init__(self,
                 sys_clk_freq, i2c_addr, regs_data,
                 i2c_freq=400e3, i2c_pins=None):

        self.sys_clk_freq = sys_clk_freq
        self.i2c_addr = i2c_addr
        self.regs_data = regs_data
        self.i2c_freq = i2c_freq
        self.i2c_pins = i2c_pins

    def regs_data_to_mem(self, regs_data):
        mem = []

        for (reg_addr, reg_val) in regs_data:
            mem.append(self.i2c_addr << 1)  # Write
            mem.append(reg_addr)
            mem.append(reg_val)

        return mem

    def elaborate(self, platform):
        m = Module()

        mem_data = self.regs_data_to_mem(self.regs_data)
        m.submodules.mem = mem = MemoryStreamReader(8, mem_data)

        i2c_period = (self.sys_clk_freq // self.i2c_freq)
        m.submodules.writer = writer = I2CWriterStream(self.i2c_pins, i2c_period)

        m.d.comb += mem.source.connect(writer.sink)

        return m

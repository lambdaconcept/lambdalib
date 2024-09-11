# 2024 - LambdaConcept - po@lambdaconcept.com

from amaranth import *

from ...interface import stream
from .stream import *
from ..mem.stream import *


class I2CRegisterInit(Elaboratable):
    """Sends an init sequence to an I2C device. I2C writer
    can be exposed for further usage (eg. readjusting 
    parameters after init)."""
    def __init__(self,
                 sys_clk_freq, i2c_addr, regs_data,
                 i2c_freq=400e3, i2c_pins=None,
                 expose_writer=False):

        self.sys_clk_freq = sys_clk_freq
        self.i2c_addr = i2c_addr
        self.regs_data = regs_data
        self.i2c_freq = i2c_freq
        self.i2c_pins = i2c_pins
        self.done = Signal()  # Asserted when init sequence has been sent

        if expose_writer:
            self.writer = stream.Endpoint([("data", 8)])
        else:
            self.writer = None

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

        with m.If(mem.source.valid & mem.source.ready & mem.source.last):
            m.d.sync += self.done.eq(1)

        if self.writer is None:
            m.d.comb += mem.source.connect(writer.sink)
        else:
            with m.If(~self.done):
                m.d.comb += [
                    mem.source.connect(writer.sink),
                    self.writer.ready.eq(0),
                ]
            with m.Else():
                m.d.comb += [
                    self.writer.connect(writer.sink),
                    mem.source.ready.eq(0),
                ]

        return m

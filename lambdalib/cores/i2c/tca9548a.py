# 2024 - LambdaConcept - po@lambdaconcept.com

from amaranth import *

from ...interface import stream
from ..i2c.stream import *


__all__ = ["TCA9548A"]


class TCA9548A(Elaboratable):
    """ Driver for TCA9548A I2C multiplexer.

    On `self.ctrl` change, an I2C write is triggered to update
    the control register of the TCA9548A multiplexer:
        byte 0: i2c_addr
        byte 1: ctrl byte

    This module `source` stream is intented to be connected to an existing
    I2CStream instance through a stream arbiter.
    """
    def __init__(self, i2c_addr=0x70):
        self.i2c_addr = i2c_addr

        self.done   = Signal()
        self.ctrl   = Signal(8)
        self.source = stream.Endpoint(i2c_stream_description)

    def elaborate(self, platform):
        source = self.source

        m = Module()

        init        = Signal()
        ctrl_r      = Signal.like(self.ctrl)
        ctrl_addr_n = Signal()

        update      = (self.ctrl != ctrl_r)

        with m.FSM():
            with m.State("IDLE"):
                with m.If(~init):
                    m.d.sync += init.eq(1)
                    m.next = "MUX"
                with m.Elif(update):
                    m.d.sync += ctrl_r.eq(self.ctrl)
                    m.next = "MUX"
                with m.Else():
                    m.d.comb += self.done.eq(1)

            with m.State("MUX"):
                m.d.comb += [
                    source.r_wn .eq(0), # Write
                    source.data .eq(Mux(~ctrl_addr_n,
                                        self.i2c_addr << 1, ctrl_r)),
                    source.last .eq(ctrl_addr_n),
                    source.valid.eq(1),
                ]
                with m.If(source.valid & source.ready):
                    m.d.sync += ctrl_addr_n.eq(~ctrl_addr_n)
                    with m.If(source.last):
                        m.next = "IDLE"

        return m

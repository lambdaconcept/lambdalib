# 2023 - LambdaConcept - po@lambdaconcept.com

from amaranth import *

from ...interface import stream
from .stream import *


__all__ = [
    "I2CProto",
]


STATUS_OK   = 0
STATUS_ERR  = 1

class I2CProto(Elaboratable):
    """ Protocol oriented wrapper around the bidirectional I2CStream.

    The main use of this module is for creating a I2C bridge from software,
    typically over UART or USB.

    Sink stream description:
        `data`: header
            header[0]: 1 == read
                       0 == write
        `data`: length
            amount of data bytes to read or write

    When writing:
        -> `sink.data`
            header
        -> `sink.data`
            length
        -> `sink.data` ... `sink.data`
            data write ...  data write
        <- `source.data`
            status

    When reading:
        -> `sink.data`
            header
        -> `sink.data`
            length
        <- `source.data`
            status
        <- `source.data` ... `source.data`
            data read    ...  data read

    """
    def __init__(self,
                 sys_clk_freq,
                 i2c_freq=400e3,
                 i2c_pins=None,
                 **kwargs):
        self.sys_clk_freq = sys_clk_freq
        self.i2c_freq = i2c_freq
        self.i2c_pins = i2c_pins
        self.kwargs = kwargs

        self.sink = stream.Endpoint([("data", 8)])
        self.source = stream.Endpoint([("data", 8)])

    def elaborate(self, platform):
        m = Module()

        i2c_period = (self.sys_clk_freq // self.i2c_freq)
        m.submodules.i2c = i2c = I2CStream(self.i2c_pins, i2c_period, **self.kwargs)

        header = Signal(8)
        length = Signal(8)
        status = Signal()

        r_wn = header[0]
        # addr = header[1:8]

        with m.FSM():

            with m.State("HEADER"):
                m.d.comb += self.sink.ready.eq(1)
                with m.If(self.sink.valid):
                    m.d.sync += header.eq(self.sink.data)
                    m.next = "LENGTH"

            with m.State("LENGTH"):
                m.d.comb += self.sink.ready.eq(1)
                with m.If(self.sink.valid):
                    m.d.sync += length.eq(self.sink.data)
                    m.next = "ADDR"

            with m.State("ADDR"):
                m.d.comb += [
                    i2c.sink.r_wn.eq(0), # Write chip address
                    i2c.sink.data.eq(header),
                    i2c.sink.last.eq(length == 0),
                    i2c.sink.valid.eq(1),
                ]
                with m.If(i2c.sink.ready):
                    with m.If(i2c.error):
                        m.next = "ERROR"

                    with m.Elif(r_wn):
                        m.next = "OK"
                    with m.Elif(length >= 1):
                        m.next = "WRITE"
                    with m.Else():
                        m.d.sync += status.eq(STATUS_OK)
                        m.next = "STATUS"

            with m.State("OK"):
                m.d.comb += [
                    self.source.data.eq(STATUS_OK),
                    self.source.valid.eq(1),
                    self.source.last.eq(1),
                ]
                with m.If(self.source.ready):
                    m.next = "READ"

            with m.State("READ"):
                m.d.comb += [
                    i2c.sink.r_wn.eq(1),
                    i2c.sink.last.eq(length == 1),
                    i2c.sink.valid.eq(1),
                ]
                m.d.comb += i2c.source.connect(self.source)

                with m.If(i2c.sink.ready):
                    m.d.sync += length.eq(length - 1)

                    with m.If(length == 1):
                        m.next = "FLUSH"

            with m.State("FLUSH"):
                m.d.comb += i2c.source.connect(self.source)
                with m.If(self.source.valid &
                          self.source.ready &
                          self.source.last):
                    m.next = "HEADER"

            with m.State("WRITE"):
                m.d.comb += [
                    i2c.sink.r_wn.eq(0),
                    i2c.sink.data.eq(self.sink.data),
                    i2c.sink.last.eq(length == 1),
                    i2c.sink.valid.eq(1),
                ]
                with m.If(i2c.sink.ready):
                    m.d.comb += self.sink.ready.eq(1)
                    m.d.sync += length.eq(length - 1)

                    with m.If(i2c.error):
                        m.next = "ERROR"
                    with m.Elif(length == 1):
                        m.d.sync += status.eq(STATUS_OK)
                        m.next = "STATUS"

            with m.State("ERROR"):
                with m.If(length >= 1):
                    m.d.comb += self.sink.ready.eq(1)
                    m.d.sync += length.eq(length - 1)
                with m.Else():
                    m.d.sync += status.eq(STATUS_ERR)
                    m.next = "STATUS"

            with m.State("STATUS"):
                m.d.comb += [
                    self.source.data.eq(status),
                    self.source.valid.eq(1),
                    self.source.last.eq(1),
                ]
                with m.If(self.source.ready):
                    m.next = "HEADER"

        return m

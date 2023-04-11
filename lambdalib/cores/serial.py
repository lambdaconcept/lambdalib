# 2022 - LambdaConcept - po@lambdaconcept.com

from amaranth import *
from amaranth.lib.cdc import *
from amaranth_stdio.serial import AsyncSerial

from .time.timer import *
from ..interface import stream


__all__ = [
    "AsyncSerialStream",
    "AsyncSerialStreamHalfDuplex",
]


class AsyncSerialStream(Elaboratable):
    """ Stream wrapper around AsyncSerial.

    Parameters
    ----------
    see AsyncSerial
    """
    def __init__(self, *args, **kwargs):
        self.serial = AsyncSerial(*args, **kwargs)
        dw = len(self.serial.rx.data)
        self.sink = stream.Endpoint([("data", dw)])
        self.source = stream.Endpoint([("data", dw)])

    def elaborate(self, platform):
        sink = self.sink
        source = self.source
        rx, tx = self.serial.rx, self.serial.tx

        m = Module()
        m.submodules.serial = self.serial

        m.d.comb += [
            tx.data.eq(sink.data),
            tx.ack.eq(sink.valid),
            sink.ready.eq(tx.rdy),
        ]

        busy = Signal()
        m.d.comb += busy.eq(source.valid & ~source.ready)

        m.d.comb += rx.ack.eq(~busy)
        with m.If(rx.ack & rx.rdy):
            m.d.sync += [
                source.data.eq(rx.data),
                source.valid.eq(1),
            ]
        with m.Elif(source.valid & source.ready):
            m.d.sync += source.valid.eq(0)

        return m


class AsyncSerialStreamHalfDuplex(AsyncSerialStream):
    def __init__(self, *, divisor, pins=None, **kwargs):
        self.pins = pins
        self.divisor = divisor
        super().__init__(divisor=divisor, **kwargs)

    def elaborate(self, platform):
        m = super().elaborate(platform)

        pin_buf = Signal()
        m.submodules += FFSynchronizer(self.pins.io.i, pin_buf, reset=1)

        m.submodules.timer = timer = WaitTimer(self.divisor)

        with m.FSM():
            with m.State("RX"):
                m.d.comb += self.serial.rx.i.eq(pin_buf)

                with m.If(~self.serial.tx.rdy): # going to transmit
                    m.next = "TX"

            with m.State("TX"):
                m.d.comb += [
                    self.pins.io.o.eq(self.serial.tx.o),
                    self.pins.io.oe.eq(1),

                    platform.request("debug").debug.eq(1),

                    self.serial.rx.i.eq(1),
                ]
                with m.If(self.serial.tx.rdy): # end of transmit
                    m.d.comb += timer.wait.eq(1)
                    with m.If(timer.done):
                        m.next = "RX"

        return m

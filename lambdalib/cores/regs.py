# 2022 - LambdaConcept - po@lambdaconcept.com

from amaranth import *

from ..interface import stream

__all__ = [
    "StreamRegs",
]


class StreamRegs(Elaboratable):
    """ Stream to regs module.

    This module allows filling multiple consecutive registers from a single
    sink stream. This can mimic a bus write to register SoC without actually
    have all of those. Handy for quick prototyping.
    """
    def __init__(self, layout, length):
        self.layout = layout
        self.length = length
        self.sink = stream.Endpoint(layout)
        for f in layout:
            setattr(self, f[0], Array(
                Signal(f[1], name=f[0]) for _ in range(length))
            )
        self.we = Array(
            Signal(1, name="we") for _ in range(length)
        )

    def elaborate(self, platform):
        sink = self.sink

        m = Module()

        idx = Signal(range(self.length))

        m.d.comb += sink.ready.eq(1)
        for k in range(self.length):
            m.d.sync += self.we[k].eq(0)

        with m.If(sink.valid):

            # Update register values
            for f in self.layout:
                val = getattr(sink, f[0])
                regs = getattr(self, f[0])

                m.d.sync += regs[idx].eq(val)
            m.d.sync += self.we[idx].eq(1)

            # Increment register address
            with m.If((idx == self.length - 1) | sink.last):
                m.d.sync += idx.eq(0)
            with m.Else():
                m.d.sync += idx.eq(idx + 1)

        return m

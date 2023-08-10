# 2021 - LambdaConcept

from amaranth import *

from ...interface import stream


__all__ = ["Multiplier"]


class Multiplier(Elaboratable):
    def __init__(self, shape_a, shape_b):
        shape_a = Shape.cast(shape_a)
        shape_b = Shape.cast(shape_b)
        shape_c = Shape(shape_a.width  +  shape_b.width,
                        shape_a.signed or shape_b.signed)

        self.i = stream.Endpoint([("a", shape_a),
                                  ("b", shape_b)])
        self.o = stream.Endpoint([("c", shape_c)])

    def elaborate(self, platform):
        i = self.i
        o = self.o

        m = Module()

        with m.If(~o.valid | o.ready):
            m.d.comb += i.ready.eq(1)
            m.d.sync += [
                o.c.eq(i.a * i.b),
                o.valid.eq(i.valid),
                o.first.eq(i.first),
                o.last .eq(i.last),
            ]

        return m

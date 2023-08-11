# 2021 - LambdaConcept

from amaranth import *

from ...interface import stream


__all__ = [
    "multiplier_layout_i",
    "multiplier_layout_o",
    "Multiplier",
]


def multiplier_layout_i(shape_a, shape_b):
    shape_a = Shape.cast(shape_a)
    shape_b = Shape.cast(shape_b)
    return [("a", shape_a), ("b", shape_b)]

def multiplier_layout_o(shape_a, shape_b):
    shape_a = Shape.cast(shape_a)
    shape_b = Shape.cast(shape_b)
    shape_c = Shape(shape_a.width  +  shape_b.width,
                    shape_a.signed or shape_b.signed)
    return [("c", shape_c)]


class Multiplier(Elaboratable):
    def __init__(self, shape_a, shape_b):
        self.i = stream.Endpoint(multiplier_layout_i(shape_a, shape_b))
        self.o = stream.Endpoint(multiplier_layout_o(shape_a, shape_b))

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

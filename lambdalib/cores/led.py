# 2022 - LambdaConcept - po@lambdaconcept.com

from amaranth import *


__all__ = ["BlinkKeep", "BlinkDomain"]


class BlinkKeep(Elaboratable):
    def __init__(self, o, i, timeout=1e6, duty=1.0):
        self.o = o
        self.i = i
        self.timeout = int(timeout)

        self.nbits = 8
        assert(self.timeout >= (2**self.nbits))
        self.thresh = int(duty * (2**self.nbits))

    def elaborate(self, platform):
        m = Module()

        counter = Signal(range(self.timeout + 1))

        with m.If(self.i):
            m.d.sync += counter.eq(self.timeout)

        with m.Elif(counter > 0):
            m.d.sync += counter.eq(counter - 1)

        with m.Else():
            m.d.sync += counter.eq(0)

        # PWM duty cycle
        inc = Signal(self.nbits)
        m.d.sync += inc.eq(inc + 1)

        m.d.comb += self.o.eq((inc < self.thresh) & (counter > 0))

        return m


class BlinkDomain(Elaboratable):
    def __init__(self, led, domain="sync"):
        self.led = led
        self.domain = domain

    def elaborate(self, platform):
        m = Module()

        counter = Signal(26)
        m.d[self.domain] += counter.eq(counter + 1)

        m.d.comb += self.led.eq(counter[-1])

        return m

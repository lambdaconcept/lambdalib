# 2022 - LambdaConcept - po@lambdaconcept.com

from amaranth import *


__all__ = [
    "PulseClock",
    "TuningClock",
]


class PulseClock(Elaboratable):
    """ Pulse generator.

    I/O:
        O: o    -- the pulse output signal, asserted during one clock
                   cycle at the target_clk frequency.
        I: rst: -- resets the accumulator register to half its value.
    """
    def __init__(self, sys_clk_freq, target_clk):
        self.tuning_word = int((target_clk / sys_clk_freq) * 2**32)
        self.o = Signal()
        self.rst = Signal()

    def elaborate(self, platform):
        m = Module()

        acc = Signal(32, reset_less=True)
        tick = Signal()

        with m.If(self.rst):
            m.d.sync += acc.eq(2**31)
        with m.Else():
            m.d.sync += Cat(acc, tick).eq(acc + self.tuning_word)
        m.d.comb += self.o.eq(tick)

        return m


class TuningClock(Elaboratable):
    def __init__(self, sys_clk_freq, target_clk):
        self.tuning_word = int((2 * target_clk / sys_clk_freq) * 2**32)
        self.o = Signal()

    def elaborate(self, platform):
        m = Module()

        acc = Signal(32, reset_less=True)
        tick = Signal()

        m.d.sync += Cat(acc, tick).eq(acc + self.tuning_word)

        with m.If(tick):
            m.d.sync += self.o.eq(~self.o)

        return m

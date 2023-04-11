from amaranth import *

class WaitTimer(Elaboratable):
    def __init__(self, t):
        self.t = t
        self.wait = Signal()
        self.done = Signal()

    def elaborate(self, platform):
        m = Module()

        count = Signal(range(self.t + 1), reset=self.t)
        m.d.comb += self.done.eq(count == 0)
        with m.If(self.wait):
            with m.If(~self.done):
                m.d.sync += count.eq(count - 1)
        with m.Else():
            m.d.sync += count.eq(count.reset)

        return m

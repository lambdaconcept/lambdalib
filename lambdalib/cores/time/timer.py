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

class WaitNTimer(Elaboratable):
    def __init__(self, ts):
        if not isinstance(ts, list):
            ts = [ts]
        self.ts   = ts
        self.wait = Signal(len(ts))
        self.done = Signal()

    def elaborate(self, platform):
        m = Module()

        count = Signal(range(max(self.ts) + 1))

        with m.If(self.wait.any()):
            with m.If(~self.done):
                m.d.sync += count.eq(count + 1)
        with m.Else():
            m.d.sync += count.eq(0)

        cond = m.If
        for i, t in enumerate(self.ts):
            with cond(self.wait[i] & (count == t)):
                m.d.comb += self.done.eq(1)
            cond = m.Elif

        return m

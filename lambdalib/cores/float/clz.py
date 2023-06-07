from amaranth import *


class CLZ(Elaboratable):
    def __init__(self):
        self.d = Signal(32)
        self.clz = Signal(5)

    def elaborate(self, platform):
        clz = self.clz
        d = self.d

        m = Module()

        for i in range(5):
            m.d.comb += clz[4-i].eq(d[16 >> i : 32 >> i] == 0)
            d = Mux(clz[4-i], d[0: 16 >> i], d[16 >> i: 32 >> i])

        return m

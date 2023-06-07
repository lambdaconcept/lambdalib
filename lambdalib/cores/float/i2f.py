from amaranth import *

from .clz import *
from ...interface import stream


__all__ = ["Int2Float"]


class Int2Float(Elaboratable):
    def __init__(self):
        self.sink   = stream.Endpoint([("data", 32)])
        self.source = stream.Endpoint([("data", 32)])

    def elaborate(self, platform):
        sink = self.sink
        source = self.source

        m = Module()

        m.submodules.clz = clz = CLZ()

        s1_valid = Signal()
        s1_sign  = Signal()
        s1_abs   = Signal(31)
        s1_zero  = Signal()
        s1_clz   = Signal(5)
        s1_last  = Signal()

        s2_valid = Signal()
        s2_sign  = Signal()
        s2_expn  = Signal(8)
        s2_mant  = Signal(31)
        s2_last  = Signal()

        m.d.comb += [
            clz.d.eq(Cat(1, s1_abs)),
            s1_clz.eq(clz.clz)
        ]

        m.d.comb += [
            source.data.eq(Cat(s2_mant[7:30], s2_expn, s2_sign)),
            source.valid.eq(s2_valid),
            source.last.eq(s2_last),
        ]

        stall = source.valid & ~source.ready
        with m.If(~stall):

            m.d.comb += sink.ready.eq(1)
            m.d.sync += [
                s1_valid.eq(sink.valid),
                s1_sign.eq(sink.data[31]),
                s1_last.eq(sink.last),
            ]

            with m.If(sink.data[31]):
                m.d.sync += s1_abs.eq(0-sink.data[0:31]),
            with m.Else():
                m.d.sync += s1_abs.eq(sink.data[0:31]),

            m.d.sync += s1_zero.eq(sink.data[0:31] == 0)

            m.d.sync += [
                s2_valid.eq(s1_valid),
                s2_sign.eq(s1_sign),
                s2_mant.eq(s1_abs << s1_clz),
                s2_last.eq(s1_last),
            ]

            with m.If(s1_zero):
                m.d.sync += s2_expn.eq(0)
            with m.Else():
                m.d.sync += s2_expn.eq(157 - Cat(s1_clz, C(0,4)))

        return m


from amaranth.sim import *
from ...interface.stream_sim import *


def test_i2f():
    dut = Int2Float()
    sim = Simulator(dut)

    data = {
        "data": [
            0x00000a76,
            0x00028880,
            0xfffff380,
            0xfff8a180,
            0xffffe0c0,
            0xfff9a700,
            0x000445c0,
         ],
        "last": [0] * 6 + [1] * 1,
    }

    tx = StreamSimSender(dut.sink, data, speed=0.3)
    rx = StreamSimReceiver(dut.source, length=7, speed=0.8, verbose=True)

    sim.add_clock(1e-6)
    sim.add_sync_process(tx.sync_process)
    sim.add_sync_process(rx.sync_process)
    with sim.write_vcd("tests/test_i2f.vcd"):
        sim.run()


if __name__ == "__main__":
    test_i2f()

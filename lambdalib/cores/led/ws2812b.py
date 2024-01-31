# 2023 - LambdaConcept - po@lambdaconcept.com

from amaranth import *

from lambdalib.interface import stream


__all__ = ["WS2812B"]


class WS2812B(Elaboratable):
    """ Driver for serial LED XINGLIGHT XL-****RGBC-WS2812B.

    24 bits format:
        G7-0 R7-0 B7-0
    """
    def __init__(self, pin, sys_clk_freq, width=24):
        self.pin = pin
        self.sys_clk_freq = sys_clk_freq
        self.width = width

        self.sink = stream.Endpoint([("data", width)])

    def elaborate(self, platform):
        pin = self.pin
        sink = self.sink
        width = self.width

        # Chip timings
        T0H  = int(0.295e-6 * self.sys_clk_freq)
        T1H  = int(0.595e-6 * self.sys_clk_freq)
        T    = int(0.890e-6 * self.sys_clk_freq)
        TRST = int(80e-6    * self.sys_clk_freq)

        m = Module()

        sreg = Signal(width)
        bit  = sreg[width-1] # Send MSB first
        cycs = Signal(range(TRST + 1))
        last = Signal()
        idx  = Signal(range(width))
        inc  = Signal()


        # Global cycles counter
        with m.If(inc):
            m.d.sync += cycs.eq(cycs + 1)
        with m.Else():
            m.d.sync += cycs.eq(0)


        with m.FSM():

            with m.State("IDLE"):
                # Accept one pixel from the input stream
                m.d.comb += sink.ready.eq(1)
                with m.If(sink.valid):
                    m.d.sync += [
                        last.eq(sink.last),
                        sreg.eq(sink.data),
                        idx .eq(0),
                    ]
                    m.next = "TRANSMIT"

            with m.State("TRANSMIT"):
                # Send bit: High part
                with m.If( ((bit == 0) & (cycs < T0H))
                         | ((bit == 1) & (cycs < T1H)) ):
                    m.d.comb += pin.eq(1)
                    m.d.comb += inc.eq(1)

                # Send bit: Low part
                with m.Elif( cycs < T ):
                    m.d.comb += inc.eq(1)

                # End of current bit: Reg shift
                with m.Elif(idx < width-1):
                    m.d.sync += [
                        idx .eq(idx + 1),
                        sreg.eq(Cat(0, sreg)),
                    ]

                # No more bits
                with m.Elif(last):
                    m.next = "RESET"
                with m.Else():
                    m.next = "IDLE"

            with m.State("RESET"):
                m.d.comb += inc.eq(1)
                with m.If(cycs >= TRST):
                    m.next = "IDLE"


        return m


from amaranth.sim import *
from lambdalib.interface.stream_sim import *


def test():
    top = WS2812B(Signal(), 100e6)
    sim = Simulator(top)

    data = {
        "data": [0xA1B2C3, 0xD4E5F6],
        "last": [       0,        0],
    }

    tx = StreamSimSender(top.sink, data, speed=0.5)

    sim.add_clock(1e-6)
    sim.add_sync_process(tx.sync_process)
    with sim.write_vcd("test_ws2812b.vcd"):
        sim.run()


if __name__ == "__main__":
    test(); print()

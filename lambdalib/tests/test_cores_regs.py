# 2022 - LambdaConcept - po@lambdaconcept.com

from amaranth import *
from amaranth.sim import *

from lambdalib.interface.stream_sim import *
from lambdalib.cores.regs import *


def test_regs():
    layout_data = [
        ("data",    8),
    ]

    regs = StreamRegs(layout_data, 5)
    sim = Simulator(regs)

    sink = {
        "data":     [0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07],
        "last":     [0,    0,    1,    0,    0,    0,    0],
    }

    sender = StreamSimSender(regs.sink, sink, speed=0.5)

    sim.add_clock(1e-6)
    sim.add_sync_process(sender.sync_process)
    with sim.write_vcd("tests/test_stream_regs.vcd"):
        sim.run()


if __name__ == "__main__":
    test_regs(); print()

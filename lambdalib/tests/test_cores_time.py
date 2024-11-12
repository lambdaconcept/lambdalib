# 2024 - LambdaConcept - po@lambdaconcept.com

from amaranth import *
from amaranth.sim import *

from ..cores.time.timer import *


def test_timer():
    cycles = 100
    timer = WaitTimer(cycles)
    sim = Simulator(timer)

    def bench():
        for i in range(15):
            yield
        yield timer.wait.eq(1)
        for i in range(200):
            yield
            expect = (i >= cycles)
            result = (yield timer.done)
            # print(result, expect)
            assert(result == expect)

    sim.add_clock(1e-6)
    sim.add_sync_process(bench)
    with sim.write_vcd("tests/test_time_timer.vcd"):
        sim.run()


def test_ntimer():
    cycles_1 = 100
    cycles_2 = 200
    timer = WaitNTimer([cycles_1, cycles_2])
    sim = Simulator(timer)

    def bench():
        for i in range(15):
            yield


        for i, cyc in enumerate(timer.ts):
            yield timer.wait[i].eq(1)
            for i in range(400):
                yield
                expect = (i >= cyc)
                result = (yield timer.done)
                # print(result, expect, cyc)
                assert(result == expect)

            yield timer.wait.eq(0)
            yield

    sim.add_clock(1e-6)
    sim.add_sync_process(bench)
    with sim.write_vcd("tests/test_time_timer.vcd"):
        sim.run()


if __name__ == "__main__":
    test_timer(); print()
    test_ntimer(); print()

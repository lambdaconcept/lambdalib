# 2023 - LambdaConcept - po@lambdaconcept.com

import math

from amaranth import *
from amaranth_soc import wishbone
from lambdasoc.soc.base import SoC
from lambdasoc.periph.timer import *

from ..cores.spi.master import *
from ..cores.spi.slave import *
from ..cores.spi.bridge import *
from ..cores.spi.common import *


from amaranth.sim import *
from ..interface.stream_sim import *


class MasterSlaveBench(Elaboratable):
    def __init__(self):
        self.sys_clk_freq = 33.3333e6
        self.spi_pins = SPIPinsStub()
        self.master = SPIPHYMaster(self.spi_pins, self.sys_clk_freq,
                                   spi_clk_freq=5e6)
        self.slave = SPIPHYSlave(self.spi_pins, width=16, stages=(16, 16, 16,))

    def elaborate(self, platform):
        m = Module()

        m.submodules.master = self.master
        m.submodules.slave  = self.slave

        return m


class SlaveLoopBench(Elaboratable):
    def __init__(self):
        self.sys_clk_freq = 33.3333e6
        self.spi_pins = SPIPinsStub()
        self.master = SPIPHYMaster(self.spi_pins, self.sys_clk_freq,
                                   spi_clk_freq=1e6)
        self.slave = SPIPHYSlave(self.spi_pins, width=16)

    def elaborate(self, platform):
        m = Module()

        m.submodules.master = self.master
        m.submodules.slave  = self.slave

        m.d.comb += self.slave.source.connect(self.slave.sink)

        return m


class WbBridgeBench(SoC, Elaboratable):
    def __init__(self):
        self.spi_pins = SPIPinsStub()

        # Bridge
        self.bridge = SPIWishboneBridge(
                width=32, addr_width=30, granularity=8)

        # Bus
        self.decoder = wishbone.Decoder(
                addr_width=30, data_width=32, granularity=8)

        # Dummy peripheral
        self.periph = TimerPeripheral(32)
        self.decoder.add(self.periph.bus, addr=None)

        self.memory_map = self.decoder.bus.memory_map

    def elaborate(self, platform):
        m = Module()

        m.submodules.periph = self.periph
        m.submodules.bridge = self.bridge
        m.submodules.decoder = self.decoder

        m.d.comb += self.bridge.bus.connect(self.decoder.bus)

        return m


def test_spi():
    top = MasterSlaveBench()
    sim = Simulator(top)

    def control():
        yield top.master.cs.eq(1)
        for i in range(1000):
            yield

        yield top.master.cs.eq(0)
        yield

    master_data = {
        "data": [0x0041, 0x0002,  0x0064, 0x0064],
        "width": [    1,      1,       1,      1],
        "mask":  [    1,      1,       1,      1],
        "len":   [   16,     16,      16,     16],
    }

    master_tx = StreamSimSender(top.master.sink, master_data, speed=0.5)
    master_rx = StreamSimReceiver(top.master.source,
                                 length=None,
                                 speed=0.8, verbose=True, strname="master_rx")

    slave_data = {
        "data": [0xab, 0xcd, 0x98, 0x76],
        "len":  [  16,   16,   16,   16],
    }

    slave_tx = StreamSimSender(top.slave.sink, slave_data, speed=0.8)
    slave_rx = StreamSimReceiver(top.slave.source,
                                 length=len(master_data["data"]),
                                 speed=0.8, verbose=True, strname="slave_rx")

    sim.add_clock(1e-6)
    sim.add_sync_process(master_tx.sync_process)
    sim.add_sync_process(master_rx.sync_process)
    sim.add_sync_process(slave_rx.sync_process)
    sim.add_sync_process(slave_tx.sync_process)
    sim.add_sync_process(control)
    with sim.write_vcd("tests/test_spi.vcd"):
        sim.run()


def test_spi_loop():
    top = SlaveLoopBench()
    sim = Simulator(top)

    def control():
        yield top.master.cs.eq(1)
        for i in range(10000):
            yield

        yield top.master.cs.eq(0)
        yield

    master_data = {
        "data": [0xa55a, 0x7ffe,  0xa55a, 0x7ffe],
        "width": [    1,      1,       1,      1],
        "mask":  [    1,      1,       1,      1],
        "len":   [   16,     16,      16,     16],
    }

    master_tx = StreamSimSender(top.master.sink, master_data, speed=0.5)
    master_rx = StreamSimReceiver(top.master.source,
                                 length=None,
                                 speed=0.8, verbose=True, strname="master_rx")

    sim.add_clock(1e-6)
    sim.add_sync_process(master_tx.sync_process)
    sim.add_sync_process(master_rx.sync_process)
    sim.add_sync_process(control)
    with sim.write_vcd("tests/test_spi_loop.vcd"):
        sim.run()


def test_spi_wb_bridge():
    top = WbBridgeBench()
    for info in top.memory_map.all_resources():
        print(info.name, hex(info.start), hex(info.end), info.width)
    sim = Simulator(top)

    wr_hdr = (1 << 0) | (5 << 2) # write | count

    slave_data = {
        "data": [wr_hdr, 0x0000, 0xabcd, 0x1],
        "len":   [   32,     32,     32,   8],
    }

    slave_tx = StreamSimSender(top.bridge.sink, slave_data, speed=0.3)
    def recv():
        yield top.bridge.source.ready.eq(1)
        yield

    sim.add_clock(1e-6)
    sim.add_sync_process(recv)
    sim.add_sync_process(slave_tx.sync_process)
    with sim.write_vcd("tests/test_spi_wb_bridge.vcd"):
        sim.run()


if __name__ == "__main__":
    test_spi(); print()
    test_spi_wb_bridge(); print()
    test_spi_loop(); print()

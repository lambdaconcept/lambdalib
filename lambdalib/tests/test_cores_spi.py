# 2023 - LambdaConcept - po@lambdaconcept.com

import math

import pytest

from amaranth import *
from amaranth_soc import wishbone
from lambdasoc.soc.base import SoC
from lambdasoc.periph.timer import *

from lambdalib.cores.spi.master import *
from lambdalib.cores.spi.slave import *
from lambdalib.cores.spi.bridge import *
from lambdalib.cores.spi.stream import *
from lambdalib.cores.spi.common import *


from amaranth.sim import *
from lambdalib.interface.stream_sim import *


class MasterSlaveBench(Elaboratable):
    def __init__(self, bus_width=1):
        self.sys_clk_freq = 100e6
        self.pins_m = SPIPinsStub(bus_width=bus_width)
        self.master = SPIPHYMaster(self.pins_m, self.sys_clk_freq,
                                   spi_clk_freq=50e6, width=8)
        self.pins_s = SPIPinsStub(bus_width=bus_width)
        self.slave  = SPIPHYSlave(self.pins_s, width=8)

    def elaborate(self, platform):
        m = Module()

        m.submodules.master = self.master
        m.submodules.slave  = self.slave
        m.d.comb += [
            self.pins_s.clk .eq(self.pins_m.clk),
            self.pins_s.cs_n.eq(self.pins_m.cs_n),
        ]

        if hasattr(self.pins_m, "mosi"):
            m.d.comb += [
                self.pins_s.mosi.eq(self.pins_m.mosi),
                self.pins_m.miso.eq(self.pins_s.miso),
            ]
        else:
            with m.If(self.pins_m.dq.oe):
                m.d.comb += self.pins_s.dq.i.eq(self.pins_m.dq.o)
            with m.If(self.pins_s.dq.oe):
                m.d.comb += self.pins_m.dq.i.eq(self.pins_s.dq.o)

        return m


class MasterStreamBench(Elaboratable):
    def __init__(self, bus_width=1):
        self.sys_clk_freq = 100e6
        self.api = SPIStream(width=8, bus_width=bus_width)
        self.pins = SPIPinsStub(bus_width=bus_width)
        self.master = SPIPHYMaster(self.pins, self.sys_clk_freq,
                                   spi_clk_freq=50e6, width=8)

    def elaborate(self, platform):
        m = Module()

        m.submodules.api = self.api
        m.submodules.master = self.master

        m.d.comb += [
            self.master.cs.eq(self.api.cs),

            self.api.phy_source.connect(self.master.sink),
            self.master.source.connect(self.api.phy_sink),
        ]

        if hasattr(self.pins, "mosi"):
            m.d.comb += self.pins.miso.eq(self.pins.mosi)
        else:
            with m.If(self.pins.dq.oe):
                m.d.comb += self.pins.dq.i.eq(self.pins.dq.o)

        return m


class SlaveLoopBench(Elaboratable):
    def __init__(self):
        self.sys_clk_freq = 33.3333e6
        self.spi_pins = SPIPinsStub()
        self.master = SPIPHYMaster(self.spi_pins, self.sys_clk_freq,
                                   spi_clk_freq=1e6, width=16)
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


def test_spi(bus_width=1):
    top = MasterSlaveBench(bus_width=bus_width)
    sim = Simulator(top)

    def control():
        yield top.master.cs.eq(1)
        for i in range(1000):
            yield

        yield top.master.cs.eq(0)
        yield

    w = bus_width
    master_data = {
        "data": [0x0041, 0x0002,  0x0064, 0x0064],
        "width": [    w,      w,       w,      w],
        "oe":    [    1,      1,       1,      1],
        "len":   [    8,      8,       8,      8],
    }

    master_tx = StreamSimSender(top.master.sink, master_data, speed=1)
    master_rx = StreamSimReceiver(top.master.source,
                                 length=None,
                                 speed=1, verbose=True, strname="master_rx")

    slave_data = {
        "data": [0xab, 0xcd, 0x98, 0x76],
        "len":  [   8,    8,    8,    8],
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
    with sim.write_vcd(f"tests/test_spi_x{bus_width}.vcd"):
        sim.run()

    slave_rx.verify({k:master_data[k] for k in ["data", "len"]})


def test_spi_stream(bus_width=1):
    top = MasterStreamBench(bus_width=bus_width)
    sim = Simulator(top)

    stream_data = {
        "data": range(16),
        "last": [0] * 15 + [1],
    }

    stream_tx = StreamSimSender(top.api.data_sink, stream_data, speed=1)
    stream_rx = StreamSimReceiver(top.api.data_source,
                                 length=len(stream_data["data"]),
                                 speed=1, verbose=True, strname="stream_rx")

    sim.add_clock(1e-6)
    sim.add_sync_process(stream_tx.sync_process)
    sim.add_sync_process(stream_rx.sync_process)
    with sim.write_vcd(f"tests/test_spi_stream_x{bus_width}.vcd"):
        sim.run()

    stream_rx.verify(stream_data)


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
        "oe":    [    1,      1,       1,      1],
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


@pytest.mark.skip(reason="Amaranth-soc internal fail")
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
    test_spi(bus_width=4); print()
    test_spi_stream(); print()
    test_spi_stream(bus_width=4); print()
    # test_spi_wb_bridge(); print()
    test_spi_loop(); print()

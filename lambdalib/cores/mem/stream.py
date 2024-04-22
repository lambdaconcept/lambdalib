# 2022 - LambdaConcept - po@lambdaconcept.com

from amaranth import *
from amaranth.sim import *

from ...interface import stream
from ...interface.stream_sim import *


__all__ = [
    "MemoryStream",
    "MemoryStreamReader",
]


class MemoryStream(Elaboratable):
    """ Store and fetch to/from memory with a stream interface.

    This module is similar to a FIFO with the exception that we cannot
    write and read at the same time, but we can read the same data
    multiple times by setting `rewind` to read again from the
    beginning of the memory.

    Intended use:
    - Write n values to the `sink` stream.
    - Rewind the MemoryStream by setting `rewind` to 1.
    - Read at most n values from the `source` stream.

    The output stream is buffered by default, e.g. a sync gate is added
    to the output stream for critical path reduction, with an additional
    clock cycle delay cost at the beginning of the read operation.
    """
    def __init__(self, dw, depth, buffered=True):
        self.dw = dw
        self.depth = depth
        self.buffered = buffered

        self.rewind = Signal()
        self.sink = stream.Endpoint([("data", dw)], name="sink_mem_i")

        if self.buffered:
            self.buffer = ResetInserter(self.rewind)(
                                stream.PipeValid([("data", dw)]))
            self.source = self.buffer.source
        else:
            self.source = stream.Endpoint([("data", dw)])

    def elaborate(self, platform):
        sink = self.sink
        source = self.buffer.sink if self.buffered else self.source

        m = Module()

        # Synchronous buffer for outgoing memory reads
        if self.buffered:
            m.submodules.buffer = self.buffer

        mem = Memory(depth=self.depth, width=self.dw)
        m.submodules.mem_wp = mem_wp = mem.write_port()
        m.submodules.mem_rp = mem_rp = mem.read_port(transparent=False)

        addr_wr = Signal.like(mem_wp.addr)
        addr_rd = Signal.like(mem_rp.addr)
        addr_nxt = Signal.like(mem_rp.addr)

        level = Signal(range(self.depth + 1))
        underflow = (addr_rd >= level)
        last = addr_rd == (level - 1)

        # Rewind the memory to the beginning
        with m.If(self.rewind):
            m.d.sync += addr_wr.eq(0)
            m.d.sync += addr_rd.eq(0)
            m.d.comb += addr_nxt.eq(0)

        # We increment the address when writing or reading,
        # and we already present the next address to the read memory port
        # to anticipate one clock cycle.
        with m.Elif(sink.valid & sink.ready):
            m.d.sync += addr_wr.eq(addr_wr + 1)
            m.d.sync += level.eq(addr_wr + 1)

        with m.Elif(source.valid & source.ready):
            m.d.comb += addr_nxt.eq(addr_rd + 1)
            m.d.sync += addr_rd.eq(addr_nxt)

        with m.Else():
            m.d.comb += addr_nxt.eq(addr_rd)

        # Write
        m.d.comb += [
            mem_wp.addr.eq(addr_wr),
            mem_wp.data.eq(sink.data),
            mem_wp.en.eq(sink.valid),
            sink.ready.eq(~self.rewind),
        ]

        # Read
        m.d.comb += [
            mem_rp.addr.eq(addr_nxt),
            mem_rp.en.eq(1),
            source.valid.eq(~self.rewind & ~sink.valid & ~underflow),
            source.data.eq(mem_rp.data),
            source.last.eq(last),
        ]

        return m


class MemoryStreamReader(Elaboratable):
    """ Read from a read-only memory with a stream interface.

    The memory is read only and is initialized at compilation time
    with the `init` buffer.

    Intended use:
    - Read at most n values from the `source` stream.
    - Rewind the MemoryStreamReader by setting `rewind` to 1.
    - Read at most n values from the `source` stream.
    - Rewind [...]

    The output stream is buffered by default, e.g. a sync gate is added
    to the output stream for critical path reduction, with an additional
    clock cycle delay cost at the beginning of the read operation.
    """
    def __init__(self, dw, init, buffered=True):
        self.dw = dw
        self.init = init
        self.buffered = buffered

        self.rewind = Signal()
        self.source = stream.Endpoint([("data", dw)], name="source_mem_o")

        if self.buffered:
            self.buffer = ResetInserter(self.rewind)(
                                stream.PipeValid([("data", dw)]))
            self.source = self.buffer.source
        else:
            self.source = stream.Endpoint([("data", dw)])

    def elaborate(self, platform):
        source = self.buffer.sink if self.buffered else self.source

        m = Module()

        # Synchronous buffer for outgoing memory reads
        if self.buffered:
            m.submodules.buffer = self.buffer

        depth = len(self.init)
        mem = Memory(depth=depth, width=self.dw, init=self.init)
        m.submodules.mem_rp = mem_rp = mem.read_port(transparent=False)

        wait = Signal(reset=1)
        done = Signal()

        addr_rd = Signal.like(mem_rp.addr)
        addr_nxt = Signal.like(mem_rp.addr)

        last = addr_rd == (depth - 1)

        # Rewind the memory to the beginning
        with m.If(self.rewind):
            m.d.sync += done.eq(0)
            m.d.sync += addr_rd.eq(0)
            m.d.comb += addr_nxt.eq(0)

        # We increment the address when reading,
        # and we already present the next address to the read memory port
        # to anticipate one clock cycle
        with m.Elif(source.valid & source.ready):
            m.d.comb += addr_nxt.eq(addr_rd + 1)
            m.d.sync += addr_rd.eq(addr_nxt)

            with m.If(last):
                m.d.sync += done.eq(1)

        with m.Else():
            m.d.comb += addr_nxt.eq(addr_rd)

        # Read
        m.d.comb += [
            mem_rp.addr.eq(addr_nxt),
            mem_rp.en.eq(1),
            source.valid.eq(~self.rewind & ~wait & ~done),
            source.data.eq(mem_rp.data),
            source.last.eq(last),
        ]

        # We wait one cycle at reset and rewind to match
        # the memory port latency.
        m.d.sync += wait.eq(self.rewind)

        return m


from amaranth.sim import *
from lambdalib.interface.stream_sim import *


def test_mem_stream():
    datas = {
        "data": [
            0x01, 0x02, 0x03, 0x04,
            0x05, 0x06, 0x07, 0x08,
        ],
        "last": [
            0, 0, 0, 0,
            0, 0, 0, 1,
        ],
    }
    length = len(datas["data"])

    dut = MemoryStream(8, 8)
    sim = Simulator(dut)

    sender = StreamSimSender(dut.sink, datas, speed=0.3)
    receiver = StreamSimReceiver(dut.source, length=length,
                                 speed=0.1, initial_delay=100,
                                 verbose=True)

    def rewind():
        for i in range(50):
            yield
        yield dut.rewind.eq(1)
        yield
        yield dut.rewind.eq(0)
        yield

    sim.add_clock(1e-6)
    sim.add_sync_process(sender.sync_process)
    sim.add_sync_process(rewind)
    sim.add_sync_process(receiver.sync_process)
    with sim.write_vcd("tests/test_mem_stream.vcd"):
        sim.run()

    receiver.verify(datas)


def test_mem_stream_reader():
    datas = {
        "data": [
            (0x69 << 1),   0xc3,   0xa5,
            (0x69 << 1),   0xd2,   0x18,
        ],
    }
    length = len(datas["data"])

    dut = MemoryStreamReader(8, datas["data"])
    sim = Simulator(dut)

    receiver = StreamSimReceiver(dut.source, length=2 * length,
                                 speed=0.9, verbose=True)

    def rewind():
        for i in range(50):
            yield
        yield dut.rewind.eq(1)
        yield
        yield dut.rewind.eq(0)
        yield

    sim.add_clock(1e-6)
    sim.add_sync_process(receiver.sync_process)
    sim.add_sync_process(rewind)
    with sim.write_vcd("tests/test_mem_stream_reader.vcd"):
        sim.run()


if __name__ == "__main__":
    test_mem_stream()
    test_mem_stream_reader()

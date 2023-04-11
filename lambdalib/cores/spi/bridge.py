# 2023 - LambdaConcept - po@lambdaconcept.com

from amaranth import *
from amaranth_soc import wishbone

from ...interface import stream
from .common import *
from .slave import *


__all__ = ["SPIWishboneBridge"]


class SPIWishboneBridge(Elaboratable):
    def __init__(self, width=32, addr_width=30, granularity=8):
        self.width = width
        self.addr_width = addr_width
        self.granularity = granularity

        self.sink = stream.Endpoint(spi_slave_layout(width))
        self.source = stream.Endpoint(spi_slave_layout(width))

        self.bus = wishbone.Interface(
            addr_width=addr_width,
            data_width=width,
            granularity=granularity,
            # features={"cti", "bte"},
        )

    def elaborate(self, platform):
        sink = self.sink
        source = self.source
        bus = self.bus

        m = Module()

        command = Record([
            ("write",       1),
            ("const",       1), # XXX NotImplemented
            ("count",       self.width - 2),
        ])
        addr = Signal.like(sink.data)
        addr_shift = self.width - self.addr_width
        wordlen = self.width // 8
        bytecount = Signal(range(wordlen + 1))
        m.d.comb += bytecount.eq(sink.len[3:]) # Divide bitcount by 8

        with m.FSM() as fsm:

            with m.State("COMMAND"):
                m.d.comb += sink.ready.eq(1)
                with m.If(sink.valid):
                    with m.If(sink.len == len(command)):
                        m.d.sync += command.eq(self.sink.data)
                        m.next = "ADDR"

            with m.State("ADDR"):
                m.d.comb += sink.ready.eq(1)
                with m.If(sink.valid):
                    with m.If(sink.len == len(addr)):
                        m.d.sync += addr.eq(self.sink.data)
                        m.next = "RUN"
                    with m.Else():
                        m.next = "COMMAND"

            with m.State("RUN"):
                m.d.comb += [
                    bus.cyc.eq(1),
                    bus.we.eq(command.write),
                    bus.adr.eq(addr[addr_shift:]),
                ]

                # Write
                with m.If(command.write):
                    m.d.comb += [
                        bus.stb.eq(sink.valid),
                        bus.sel.eq(2**len(bus.sel) - 1), # XXX fix this bytecount
                        bus.dat_w.eq(sink.data),
                        sink.ready.eq(bus.ack),
                    ]
                # Read
                with m.Else():
                    m.d.comb += [
                        bus.stb.eq(source.ready),
                        bus.sel.eq(2**len(bus.sel) - 1),
                        source.data.eq(bus.dat_r),
                        source.len.eq(self.width),
                        source.valid.eq(bus.ack),
                        source.last.eq(command.count <= wordlen),
                    ]

                with m.If(bus.stb & bus.ack):
                    m.d.sync += command.count.eq(command.count - wordlen)
                    m.d.sync += addr.eq(addr + wordlen)

                    with m.If((command.count <= wordlen) |
                              (command.write & (sink.len < self.width))):
                        m.next = "COMMAND"

        return m

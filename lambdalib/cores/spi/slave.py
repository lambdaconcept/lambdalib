# 2023 - LambdaConcept - po@lambdaconcept.com

from amaranth import *
from amaranth.lib.cdc import *

from .common import *
from ...interface import stream


__all__ = ["SPIPHYSlave"]


class SPIPHYSlave(Elaboratable):
    """
    Limitation: does not put last on the source stream.
    """
    def __init__(self, pins,
            cpol=0, cpha=0,
            # XXX doc for stages
            width=32, with_len=True, stages=None):

        if pins is None:
            pins = SPIPinsStub()
        self.pins = pins
        self.cpol = cpol
        self.cpha = cpha

        self.width = width
        self.with_len = with_len
        if not with_len:
            assert(stages is None)
        if stages is None:
            stages = [width]
        for n in stages:
            assert(n <= width)
        self.stages = stages

        layout = spi_slave_layout(width, with_len=with_len)
        self.sink = stream.Endpoint(layout)
        self.fifo = stream.SyncFIFO(layout, 8, buffered=True)
        self.source = self.fifo.source

    def elaborate(self, platform):
        sink = self.sink
        fifo = self.fifo

        m = Module()
        m.submodules.fifo = fifo

        clk  = Signal()
        cs_n = Signal()
        mosi = Signal()

        # Resynchronise input signals to sys clk
        m.submodules += FFSynchronizer(self.pins.clk,  clk)
        m.submodules += FFSynchronizer(self.pins.cs_n, cs_n)
        m.submodules += FFSynchronizer(self.pins.mosi, mosi)

        clk_r = Signal()
        m.d.sync += clk_r.eq(clk)

        en = ~cs_n
        rise = en & ~clk_r &  clk
        fall = en &  clk_r & ~clk

        # SPI clock modes CPOL/CPHA
        mode = (self.cpol, self.cpha)
        if mode == (0, 0) or mode == (1, 1):
            sample = rise
            update = fall
        else:
            sample = fall
            update = rise

        if self.with_len:
            wdlen = sink.len
            wdshift = (len(sink.data) - wdlen).as_unsigned()
        else:
            wdlen = self.width
            wdshift = (len(sink.data) - wdlen)

        # MOSI (input) data path
        cnt_in = Signal(range(self.width + 1))
        reg_in = Signal(self.width)
        end = ((cnt_in > 0) & ~en)

        m.d.comb += fifo.sink.data.eq(reg_in)
        if self.with_len:
            m.d.comb += fifo.sink.len.eq(cnt_in)

        # MOSI presplit in stages
        nbits = Array(self.stages)
        idx = Signal(range(len(self.stages)))

        # MOSI shift in
        with m.If(sample):
            m.d.sync += [
                reg_in.eq(Cat(mosi, reg_in[:-1])),
                cnt_in.eq(cnt_in + 1),
            ]

        # MOSI stream out
        with m.Elif((cnt_in == nbits[idx]) | end):
            m.d.comb += fifo.sink.valid.eq(1) # Assumes FIFO always ready
            m.d.sync += cnt_in.eq(0)

            with m.If(end):
                m.d.sync += idx.eq(0)
            with m.Elif(idx < len(self.stages) - 1):
                m.d.sync += idx.eq(idx + 1)

        # MISO (output) data path
        cnt_out = Signal(range(self.width + 1))
        reg_out = Signal(self.width)

        # MISO stream in
        with m.If(cnt_out == 0):
            m.d.comb += sink.ready.eq(1)
            with m.If(sink.valid):
                m.d.sync += [
                    reg_out.eq(sink.data << wdshift),
                    cnt_out.eq(wdlen),
                ]

        # MISO shift out
        with m.Elif(update):
            m.d.sync += [
                reg_out.eq(Cat(C(0, 1), reg_out[:-1])),
                self.pins.miso.eq(reg_out[-1]),
            ]
            with m.If(cnt_out > 0):
                m.d.sync += cnt_out.eq(cnt_out - 1)

        with m.Elif(~en):
            m.d.sync += cnt_out.eq(0)

        return m

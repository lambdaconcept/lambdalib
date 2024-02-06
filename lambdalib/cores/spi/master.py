#
# This file is part of LiteSPI
#
# Copyright (c) 2020-2021 Antmicro <www.antmicro.com>
# Copyright (c) 2021 Florent Kermarrec <florent@enjoy-digital.fr>
# SPDX-License-Identifier: BSD-2-Clause

# Translated and rewritten from migen/litex to amaranth
# https://github.com/litex-hub/litespi/blob/master/litespi/phy/generic_sdr.py

import math
import logging

from amaranth import *

from .common import *
from .clkgen import *
from ...interface import stream
from ..time.timer import *


__all__ = ["SPIPHYMaster"]


def SPIPHYMaster(pins, sys_clk_freq, width=8, spi_clk_freq=10e6, spi_cs_delay=2):
        # LiteSPISDRPHYCore does not support frequencies higher than sys_clk_freq / 2.
        max_freq = sys_clk_freq // 2
        if spi_clk_freq > max_freq:
            spi_clk_freq = max_freq
            logging.warning("SPIPHYMaster clock frequency limited to: {:0.3f} MHz" \
                    .format(spi_clk_freq / 1e6))
        div = math.ceil((sys_clk_freq / spi_clk_freq / 2) - 1)
        cs_delay = math.ceil(spi_cs_delay * sys_clk_freq / spi_clk_freq)

        real_freq = sys_clk_freq / 2 / (div + 1)
        logging.warning("SPIPHYMaster clock frequency set to {:0.3f} MHz" \
                .format(real_freq / 1e6))
        return _LiteSPISDRPHYCore(pins, width=width, divisor=div, cs_delay=cs_delay)


class _LiteSPISDRPHYCore(Elaboratable):
    def __init__(self, pads, width=8, divisor=1, cs_delay=0):
        # assert(divisor >= 1)
        self.pads = pads
        self.width = width
        self.divisor = divisor
        self.cs_delay = cs_delay

        self.cs = Signal()
        self.sink = stream.Endpoint(spi_core2phy_layout(width))
        self.source = stream.Endpoint(spi_phy2core_layout(width))

    def elaborate(self, platform):
        sink = self.sink
        pads = self.pads

        m = Module()

        m.submodules.fifo = fifo = stream.SyncFIFO(self.source.description, 8,
                                                   buffered=True)
        m.d.comb += fifo.source.connect(self.source)

        # Clock Generator.
        m.submodules.clkgen = clkgen = LiteSPIClkGen(pads, with_ddr=False)
        m.d.comb += [
            clkgen.div.eq(self.divisor),
            clkgen.sample_cnt.eq(1),
            clkgen.update_cnt.eq(1),
        ]

        # CS control.
        # Ensure cs_delay cycles between XFers.
        m.submodules.cs_timer = cs_timer = WaitTimer(self.cs_delay + 1)
        cs_enable = Signal()
        m.d.comb += cs_timer.wait.eq(self.cs)
        m.d.comb += cs_enable.eq(cs_timer.done)
        m.d.comb += pads.cs_n.eq(~cs_enable)

        if hasattr(pads, "mosi"):
            dq_o  = Signal()
            dq_i  = Signal(2)
            dq_oe = Signal() # Unused.
            m.d.comb += [
                pads.mosi.eq(dq_o),
                dq_i[1].eq(pads.miso),
            ]
        else:
            dq_o  = Signal(len(pads.dq.o))
            dq_i  = Signal(len(pads.dq.i))
            dq_oe = Signal(len(pads.dq.oe))
            m.d.comb += [
                pads.dq.o.eq(dq_o),
                pads.dq.oe.eq(dq_oe),
                dq_i.eq(pads.dq.i),
            ]

        if hasattr(pads, "hold_n"):
            m.d.comb += pads.hold_n.eq(1)
        if hasattr(pads, "wp_n"):
            m.d.comb += pads.wp_n.eq(1)

        # Data Shift Registers.
        sr_out_cnt   = Signal(8, reset_less=True)
        sr_out_load  = Signal()
        sr_out_shift = Signal()
        sr_out       = Signal(len(sink.data), reset_less=True)
        sr_out_end   = Signal()

        sr_in_cnt    = Signal(8, reset_less=True)
        sr_in_load   = Signal()
        sr_in_shift  = Signal()
        sr_in        = Signal(len(sink.data), reset_less=True)
        sr_in_end    = Signal()

        width_r      = Signal.like(sink.width)
        last_r       = Signal()

        # Data Out Generation/Load/Shift.
        with m.Switch(width_r):
            for i in [1, 2, 4, 8]:
                with m.Case(i):
                    m.d.comb += dq_o.eq(sr_out[-i:])

        with m.If(sr_out_load):
            m.d.sync += [
                sr_out .eq(sink.data << (len(sink.data) - sink.len).as_unsigned()),
                width_r.eq(sink.width),
                dq_oe  .eq(sink.oe),
                last_r .eq(sink.last),
            ]
            m.d.comb += sink.ready.eq(1)

        with m.Elif(sr_out_shift):
            with m.Switch(width_r):
                for i in [1, 2, 4, 8]:
                    with m.Case(i):
                        m.d.sync += sr_out.eq(Cat(Signal(i), sr_out))

        # Data In Shift.
        with m.If(sr_in_shift):
            with m.Switch(width_r):
                with m.Case(1):
                    m.d.sync += sr_in.eq(Cat(dq_i[1], sr_in))
                for i in [2, 4, 8]:
                    with m.Case(i):
                        m.d.sync += sr_in.eq(Cat(dq_i[:i], sr_in))

        with m.If(sr_in_end):
            m.d.sync += fifo.sink.valid.eq(1) # FIFO ready is checked beforehand
            m.d.sync += fifo.sink.last.eq(last_r)
        with m.Else():
            m.d.sync += fifo.sink.valid.eq(0)

        m.d.comb += fifo.sink.data.eq(sr_in)

        xfr_en = Signal()
        running = Signal()
        m.d.comb += xfr_en.eq(cs_enable & sink.valid & fifo.sink.ready)

        # Generate Clk.
        m.d.comb += clkgen.en.eq(running)

        # Wait for Start Condition.
        with m.If((~running | sr_out_end) & xfr_en):
            m.d.sync += running.eq(1)

            # Load Shift Register Count/Data Out.
            m.d.comb += sr_out_load.eq(1)
            m.d.sync += sr_out_cnt.eq(sink.len - sink.width)

            m.d.sync += sr_in_load.eq(1)
            m.d.sync += sr_in_cnt.eq(sink.len - sink.width)

        # Stop transmission.
        with m.Elif(sr_out_end & ~xfr_en):
            m.d.sync += running.eq(0)

        # Data In Shift.
        with m.If(clkgen.posedge_reg):
            m.d.comb += sr_in_shift.eq(1)

            # End XFer.
            with m.If(sr_in_cnt == 0):
                m.d.comb += sr_in_end.eq(1)
            with m.Else():
                m.d.sync += sr_in_cnt.eq(sr_in_cnt - width_r)

        # Data Out Shift.
        with m.If(clkgen.negedge):
            m.d.comb += sr_out_shift.eq(1)

            # End XFer.
            with m.If(sr_out_cnt == 0):
                m.d.comb += sr_out_end.eq(1)
            with m.Else():
                m.d.sync += sr_out_cnt.eq(sr_out_cnt - width_r)

        return m

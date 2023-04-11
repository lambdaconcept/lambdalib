#
# This file is part of LiteSPI
#
# Copyright (c) 2020-2021 Antmicro <www.antmicro.com>
# Copyright (c) 2021 Florent Kermarrec <florent@enjoy-digital.fr>
# SPDX-License-Identifier: BSD-2-Clause

# Translated from migen/litex to amaranth
# https://github.com/litex-hub/litespi/blob/master/litespi/phy/generic_sdr.py

import math
import logging

from amaranth import *

from .common import *
from .clkgen import *
from ...interface import stream
from ..time.timer import *


__all__ = ["SPIPHYMaster"]


def SPIPHYMaster(pins, sys_clk_freq, spi_clk_freq=10e6, cs_delay=10):
        # It seems that LiteSPISDRPHYCore does not support frequencies
        # higher than sys_clk_freq / 4.
        max_freq = sys_clk_freq // 4
        if spi_clk_freq > max_freq:
            spi_clk_freq = max_freq
            logging.warning("SPIPHYMaster clock frequency limited to: {} Hz".format(spi_clk_freq))
        div = math.ceil((sys_clk_freq / spi_clk_freq / 2) - 1)
        return LiteSPISDRPHYCore(pins, default_divisor=div, cs_delay=cs_delay)


# LiteSPI PHY Core ---------------------------------------------------------------------------------

class LiteSPISDRPHYCore(Elaboratable):
    def __init__(self, pads, default_divisor, cs_delay):
        assert(default_divisor >= 1)
        self.pads             = pads
        self.cs_delay         = cs_delay
        self.source           = source = stream.Endpoint(spi_phy2core_layout)
        self.sink             = sink   = stream.Endpoint(spi_core2phy_layout)
        self.cs               = Signal()
        self.spi_clk_divisor = Signal(8, reset=default_divisor)

    def elaborate(self, platform):
        sink = self.sink
        source = self.source
        pads = self.pads

        m = Module()

        # Clock Generator.
        m.submodules.clkgen = clkgen = LiteSPIClkGen(pads, with_ddr=False)
        m.d.comb += [
            clkgen.div.eq(self.spi_clk_divisor),
            clkgen.sample_cnt.eq(1),
            clkgen.update_cnt.eq(1),
        ]

        # CS control.
        cs_timer  = WaitTimer(self.cs_delay + 1) # Ensure cs_delay cycles between XFers.
        cs_enable = Signal()
        m.submodules += cs_timer
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
            raise NotImplementedError

        if hasattr(pads, "hold_n"):
            m.d.comb += pads.hold_n.eq(1)
        if hasattr(pads, "wp_n"):
            m.d.comb += pads.wp_n.eq(1)

        # Data Shift Registers.
        sr_cnt       = Signal(8, reset_less=True)
        sr_out_load  = Signal()
        sr_out_shift = Signal()
        sr_out       = Signal(len(sink.data), reset_less=True)
        sr_in_shift  = Signal()
        sr_in        = Signal(len(sink.data), reset_less=True)

        # Data Out Generation/Load/Shift.
        m.d.comb += dq_oe.eq(sink.mask)
        with m.Switch(sink.width):
            for i in [1, 2, 4, 8]:
                with m.Case(i):
                    m.d.comb += dq_o.eq(sr_out[-i:])

        with m.If(sr_out_load):
            m.d.sync += sr_out.eq(sink.data << (len(sink.data) - sink.len))

        with m.If(sr_out_shift):
            with m.Switch(sink.width):
                for i in [1, 2, 4, 8]:
                    with m.Case(i):
                        m.d.sync += sr_out.eq(Cat(Signal(i), sr_out))

        # Data In Shift.
        with m.If(sr_in_shift):
            with m.Switch(sink.width):
                with m.Case(1):
                    m.d.sync += sr_in.eq(Cat(dq_i[1], sr_in))
                for i in [2, 4, 8]:
                    with m.Case(i):
                        m.d.sync += sr_in.eq(Cat(dq_i[:i], sr_in))
        m.d.comb += source.data.eq(sr_in)

        # FSM.
        with m.FSM(reset="WAIT-CMD-DATA"):
            with m.State("WAIT-CMD-DATA"):
                # Wait for CS and a CMD from the Core.
                with m.If(cs_enable & sink.valid):
                    # Load Shift Register Count/Data Out.
                    m.d.sync += sr_cnt.eq(sink.len - sink.width)
                    m.d.comb += sr_out_load.eq(1)
                    # Start XFER.
                    m.next = "XFER"

            with m.State("XFER"):
                # Generate Clk.
                m.d.comb += clkgen.en.eq(1),

                # Data In Shift.
                with m.If(clkgen.posedge_reg2):
                    m.d.comb += sr_in_shift.eq(1)

                # Data Out Shift.
                with m.If(clkgen.negedge):
                    m.d.comb += sr_out_shift.eq(1)

                # Shift Register Count Update/Check.
                with m.If(clkgen.negedge):
                    m.d.sync += sr_cnt.eq(sr_cnt - sink.width)
                    # End XFer.
                    with m.If(sr_cnt == 0):
                        m.next = "XFER-END"

            with m.State("XFER-END"):
                # Last data already captured in XFER when divisor > 0
                # so only capture for divisor == 0.
                with m.If((self.spi_clk_divisor > 0) | clkgen.posedge_reg2):
                    # Accept CMD.
                    m.d.comb += sink.ready.eq(1),
                    # Capture last data (only for spi_clk_divisor == 0).
                    m.d.comb += sr_in_shift.eq(self.spi_clk_divisor == 0),
                    # Send Status/Data to Core.
                    m.next = "SEND-STATUS-DATA"

            with m.State("SEND-STATUS-DATA"):
                # Send Data In to Core and return to WAIT when accepted.
                m.d.comb += [
                    source.valid.eq(1),
                    source.last.eq(1),
                ]
                with m.If(source.ready):
                    m.next = "WAIT-CMD-DATA"

        return m

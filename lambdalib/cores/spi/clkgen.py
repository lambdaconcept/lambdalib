#
# This file is part of LiteSPI
#
# Copyright (c) 2020 Antmicro <www.antmicro.com>
# SPDX-License-Identifier: BSD-2-Clause

# Translated from migen/litex to amaranth
# https://github.com/litex-hub/litespi/blob/master/litespi/clkgen.py

from amaranth import *

class LiteSPIClkGen(Elaboratable):
    def __init__(self, pads, cnt_width=8, with_ddr=False):
        self.pads       = pads
        self.cnt_width  = cnt_width
        self.with_ddr   = with_ddr

        self.div        = Signal(cnt_width)
        self.sample_cnt = Signal(cnt_width)
        self.update_cnt = Signal(cnt_width)

        self.posedge    = Signal()
        self.negedge    = Signal()
        self.sample     = Signal()
        self.update     = Signal()
        self.en         = Signal()
        self.posedge_reg  = Signal()
        self.posedge_reg2 = Signal()

    def elaborate(self, platform):
        m = Module()

        en = self.en
        div = self.div
        cnt = Signal(self.cnt_width)
        en_int = Signal()
        clk = Signal()

        m.d.comb += [
            self.posedge.eq(en & ~clk & (cnt == div)),
            self.negedge.eq(en & clk & (cnt == div)),
            self.sample.eq(cnt == self.sample_cnt),
            self.update.eq(cnt == self.update_cnt),
        ]

        m.d.sync += [
            self.posedge_reg.eq(self.posedge),
            self.posedge_reg2.eq(self.posedge_reg),
        ]

        with m.If(en | en_int):
            with m.If(cnt < div):
                m.d.sync += cnt.eq(cnt + 1)
            with m.Else():
                m.d.sync += [
                    cnt.eq(0),
                    clk.eq(~clk),
                ]

        with m.Else():
            m.d.sync += [
                clk.eq(0),
                cnt.eq(0),
            ]

        if not hasattr(self.pads, "clk"):
            # Clock output needs to be registered like an SDROutput.
            clk_reg = Signal()
            m.d.sync += clk_reg.eq(clk)

            if platform.device.startswith("LFE5U"):
                m.submodules += Instance("USRMCLK",
                    i_USRMCLKI  = clk_reg,
                    i_USRMCLKTS = 0
                )
            else:
                raise NotImplementedError
        else:
            m.d.comb += self.pads.clk.eq(clk)

        return m

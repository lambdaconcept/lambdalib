# 2022 - LambdaConcept - po@lambdaconcept.com

import logging

from amaranth import *
from amaranth.lib.cdc import ResetSynchronizer

from luna.gateware.architecture.car import PHYResetController
from lambdasoc.cores.pll.xilinx_7series import PLL_Xilinx7Series
from lambdasoc.cores.pll.lattice_ecp5 import PLL_LatticeECP5


__all__ = [
    "CRG_Xilinx7Series",
    "CRG_LatticeECP5",
]

class _CRG(Elaboratable):
    def __init__(self, sync_clk_freq,
                       ref_clk=None, ref_clk_freq=None,
                       has_ulpi=True):
        self.sync_clk_freq = sync_clk_freq
        self.ref_clk = ref_clk
        self.ref_clk_freq = ref_clk_freq
        self.has_ulpi = has_ulpi

    def elaborate(self, platform):
        m = Module()

        if self.ref_clk is None:
            self.ref_clk = platform.request(platform.default_clk, 0).i
        if self.ref_clk_freq is None:
            self.ref_clk_freq = int(platform.default_clk_frequency)
        logging.warning("Input ref clock: {}".format(self.ref_clk_freq))

        # External reference clock
        m.domains += ClockDomain("_ref", reset_less=platform.default_rst is None, local=True)
        m.d.comb += ClockSignal("_ref").eq(self.ref_clk)
        if platform.default_rst is not None:
            m.d.comb += ResetSignal("_ref").eq(platform.request(platform.default_rst, 0).i)

        # Sync clock
        m.domains += ClockDomain("sync")
        sync_pll_params = self.pll_cls.Parameters(
            i_domain     = "_ref",
            i_freq       = self.ref_clk_freq,
            i_reset_less = platform.default_rst is None,
            o_domain     = "sync",
            o_freq       = self.sync_clk_freq,
        )

        m.domains += ClockDomain("usb")
        if not self.has_ulpi:
            sync_pll_params.add_secondary_output(domain="usb", freq=12e6)
        logging.warning("No clock constraint on usb clock!")
        # platform.add_clock_constraint(ClockSignal("usb"), 60e6)

        # PLL
        m.submodules.sync_pll = sync_pll = self.pll_cls(sync_pll_params)
        if platform.default_rst is not None:
            sync_pll_arst = ~sync_pll.locked | ResetSignal("_ref")
        else:
            sync_pll_arst = ~sync_pll.locked
        m.submodules += ResetSynchronizer(sync_pll_arst, domain="sync")

        # USB clocks
        if self.has_ulpi:
            m.submodules.usb_reset = controller = PHYResetController()
            m.d.comb += ResetSignal("usb").eq(controller.phy_reset)

        else:
            m.domains += ClockDomain("usb_io")
            m.d.comb += [
                ResetSignal("usb").eq(sync_pll_arst),           # 12 Mhz
                ClockSignal("usb_io").eq(ClockSignal("sync")),  # 48 Mhz
                ResetSignal("usb_io").eq(sync_pll_arst),
            ]

        return m


class CRG_Xilinx7Series(_CRG):
    pll_cls = PLL_Xilinx7Series

class CRG_LatticeECP5(_CRG):
    pll_cls = PLL_LatticeECP5

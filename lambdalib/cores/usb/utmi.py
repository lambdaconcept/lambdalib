# 2024 - LambdaConcept - jean@lambdaconcept.com
import importlib

from amaranth import *
from luna.gateware.interface.utmi import UTMIInterface


class UTMITranslator(Elaboratable):
    """ULPI-UTMI translator for LUNA wrapping around ultraembedded's core."""
    def __init__(self, ulpi):
        self._ulpi = ulpi
        self.utmi = UTMIInterface()

    def elaborate(self, platform):
        m = Module()

        m.submodules.translator = translator = Instance("ulpi_wrapper",
            i_ulpi_clk60_i=ClockSignal(),
            i_ulpi_rst_i=ResetSignal(),
            i_ulpi_data_out_i=self._ulpi.data.i,
            i_ulpi_dir_i=self._ulpi.dir.i,
            i_ulpi_nxt_i=self._ulpi.nxt.i,
            i_utmi_data_out_i=self.utmi.tx_data,
            i_utmi_txvalid_i=self.utmi.tx_valid,
            i_utmi_op_mode_i=self.utmi.op_mode,
            i_utmi_xcvrselect_i=self.utmi.xcvr_select,
            i_utmi_termselect_i=self.utmi.term_select,
            i_utmi_dppulldown_i=self.utmi.dp_pulldown,
            i_utmi_dmpulldown_i=self.utmi.dm_pulldown,
            o_ulpi_data_in_o=self._ulpi.data.o,
            o_ulpi_stp_o=self._ulpi.stp.o,
            o_utmi_data_in_o=self.utmi.rx_data,
            o_utmi_txready_o=self.utmi.tx_ready,
            o_utmi_rxvalid_o=self.utmi.rx_valid,
            o_utmi_rxactive_o=self.utmi.rx_active,
            o_utmi_rxerror_o=self.utmi.rx_error,
            o_utmi_linestate_o=self.utmi.line_state)
        instance_file = importlib.resources.files() / "ulpi_wrapper.v"
        with instance_file.open("rt") as f:
            platform.add_file("ulpi_wrapper.v", f)

        # POR
        por_cycles = int(60e6 * 2e-6)  # 2us reset
        por_cnt = Signal(range(por_cycles), reset=por_cycles - 1)
        with m.If(por_cnt > 0):
            m.d.sync += por_cnt.eq(por_cnt - 1)
        por_active = Signal()
        m.d.comb += por_active.eq(por_cnt > 0)

        # UTMI signals not handled by the translator
        m.d.comb += [
            self.utmi.session_end.eq(0),
            self.utmi.suspend.eq(0),
        ]

        # ULPI signals not handled by the translator
        m.d.comb += [
            self._ulpi.data.oe.eq(~self._ulpi.dir.i),
            self._ulpi.rst.o.eq(por_active),
        ]

        return m

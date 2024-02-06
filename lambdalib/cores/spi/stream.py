# 2023 - LambdaConcept - po@lambdaconcept.com

from amaranth import *

from .common import *
from ...interface import stream


__all__ = ["SPIStream"]


def spi_stream_layout(width):
    return [("data", width)]


class SPIStream(Elaboratable):
    def __init__(self, width=8, bus_width=1):
        self.width = width
        self.bus_width = bus_width

        self.cs = Signal()

        self.phy_sink    = stream.Endpoint(spi_phy2core_layout(width))
        self.phy_source  = stream.Endpoint(spi_core2phy_layout(width))

        self.data_sink   = stream.Endpoint(spi_stream_layout(width))
        self.data_source = stream.Endpoint(spi_stream_layout(width))

    def elaborate(self, platform):
        psink   = self.phy_sink
        psource = self.phy_source
        dsink   = self.data_sink
        dsource = self.data_source

        m = Module()

        tx_en = Signal()
        rx_en = Signal()

        # MOSI data path
        m.d.comb += [
            psource.width.eq(self.bus_width),
            psource.oe.eq(1),

            psource.data.eq(dsink.data),
            psource.len.eq(len(dsink.data)),

            psource.valid.eq(dsink.valid & tx_en),
            dsink.ready.eq(psource.ready & tx_en),

            psource.last.eq(dsink.last),
        ]

        # MISO data path
        m.d.comb += [
            dsource.data.eq(psink.data[:len(dsource.data)]),

            dsource.valid.eq(psink.valid & rx_en),
            psink.ready.eq(dsource.ready & rx_en),

            dsource.last.eq(psink.last),
        ]

        with m.FSM():
            with m.State("IDLE"):
                # Incoming data starts the SPI exchange
                with m.If(dsink.valid):
                    m.next = "TX_RX"

            with m.State("TX_RX"):
                # Enable both transmit and receive paths
                m.d.comb += [
                    self.cs.eq(1),

                    tx_en.eq(1),
                    rx_en.eq(1),
                ]

                with m.If(dsink.valid & dsink.ready & dsink.last):
                    m.next = "RX"

            with m.State("RX"):
                # For the last word, only enable the receive path
                m.d.comb += [
                    self.cs.eq(1),

                    rx_en.eq(1),
                ]

                with m.If(psink.valid & psink.ready & psink.last):
                    m.next = "IDLE"

        return m

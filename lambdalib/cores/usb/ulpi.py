# 2019 - LambdaConcept
# This is a simplified version of:
# https://github.com/lambdaconcept/lambdaUSB/blob/master/lambdausb/io/ulpi.py

from amaranth import *
from amaranth.hdl.rec import *

from ...interface import stream


__all__ = ["DirectULPI"]


class DirectULPI(Elaboratable):
    def __init__(self, pins, rx_depth=32, tx_depth=32):
        self.sink   = stream.Endpoint([("data", 8)])
        self.source = stream.Endpoint([("data", 8)])

        self.rx_depth = rx_depth
        self.tx_depth = tx_depth
        self._pins = pins

    def elaborate(self, platform):
        m = Module()

        m.domains += ClockDomain("ulpi", local=True)

        m.submodules.xcvr     = xcvr     = _Transceiver(domain="ulpi", pins=self._pins)
        m.submodules.timer    = timer    = _Timer()
        m.submodules.splitter = splitter = _Splitter()
        m.submodules.sender   = sender   = _Sender()

        m.submodules.rx_fifo = rx_fifo = stream.AsyncFIFO(
            [("data", 8)], self.rx_depth, w_domain="ulpi", r_domain="sync")
        m.submodules.tx_fifo = tx_fifo = stream.AsyncFIFO(
            [("data", 8)], self.tx_depth, w_domain="sync", r_domain="ulpi")

        m.d.comb += [
            self.sink.connect(tx_fifo.sink),
            tx_fifo.source.connect(sender.sink),

            splitter.source.connect(rx_fifo.sink),
            rx_fifo.source.connect(self.source),
        ]

        with m.FSM(domain="ulpi"):
            with m.State("RESET-0"):
                m.d.comb += xcvr.rst.eq(1)
                m.d.comb += timer.cnt2us.eq(1)
                with m.If(timer.done):
                    m.next = "RESET-1"

            with m.State("RESET-1"):
                m.d.comb += timer.cnt4ms.eq(1)
                with m.If(timer.done):
                    m.next = "INIT-0"

            with m.State("INIT-0"):
                # Write Function Control register.
                m.d.comb += [
                    xcvr.sink.data.eq(0x80 | 0x4),
                    xcvr.sink.valid.eq(1)
                ]
                with m.If(xcvr.sink.ready):
                    m.next = "INIT-1"

            with m.State("INIT-1"):
                # XcvrSelect = 00 (Enable HS transceiver)
                # TermSelect =  0 (Peripheral HS)
                # OpMode     = 00 (Normal mode)
                # Reset      =  1
                # SuspendM   =  1 (Powered)
                # Reserved   =  0
                m.d.comb += [
                    xcvr.sink.data.eq(0b01100000),
                    xcvr.sink.last.eq(1),
                    xcvr.sink.valid.eq(1),
                ]
                with m.If(xcvr.sink.ready):
                    m.next = "INIT-2"

            with m.State("INIT-2"):
                m.d.comb += timer.cnt2us.eq(1)
                with m.If(timer.done):
                    m.next = "INIT-3"

            with m.State("INIT-3"):
                # Write OTG Control register.
                m.d.comb += [
                    xcvr.sink.data.eq(0x80 | 0xa),
                    xcvr.sink.valid.eq(1)
                ]
                with m.If(xcvr.sink.ready):
                    m.next = "INIT-4"

            with m.State("INIT-4"):
                # DpPullDown = 0 (Disable D+ pull-down resistor)
                # DmPullDown = 0 (Disable D- pull-down resistor)
                m.d.comb += [
                    xcvr.sink.data.eq(0b00000000),
                    xcvr.sink.last.eq(1),
                    xcvr.sink.valid.eq(1)
                ]
                with m.If(xcvr.sink.ready):
                    m.next = "LINK-UP"

            with m.State("LINK-UP"):
                m.d.comb += [
                    xcvr.source.connect(splitter.sink),
                    sender.source.connect(xcvr.sink),
                ]

        return m


class _Transceiver(Elaboratable):
    def __init__(self, domain="ulpi", pins=None):
        self.sink   = stream.Endpoint([("data", 8)])
        self.source = stream.Endpoint([("data", 8), ("cmd", 1)])

        self.rst  = Signal()
        self.dir  = Signal()
        self.nxt  = Signal()
        self.stp  = Signal()
        self.data = Record([("i", 8), ("o", 8), ("oe", 1)])

        self._domain = domain
        self._pins   = pins

    def elaborate(self, platform):
        m = Module()

        if self._pins is not None:
            m.d.comb += [
                ClockSignal(self._domain).eq(self._pins.clk.i),
                self.dir.eq(self._pins.dir.i),
                self.nxt.eq(self._pins.nxt.i),
                self.data.i.eq(self._pins.data.i),
                self._pins.data.o.eq(self.data.o),
                self._pins.data.oe.eq(self.data.oe),
                self._pins.rst.o.eq(self.rst),
                self._pins.stp.o.eq(self.stp),
            ]

        dir_r = Signal()
        m.d[self._domain] += dir_r.eq(self.dir)

        # Transmit
        with m.If(~dir_r & ~self.dir):
            m.d.comb += self.data.oe.eq(1)
            with m.If(~self.stp):
                with m.If(self.sink.valid):
                    # Once transmission has begun, the stream has to be valid
                    # all the time until the last data byte otherwise crap
                    # will be sent: There is no way to throttle the output.
                    m.d.comb += self.data.o.eq(self.sink.data)
                    with m.If(self.sink.last & self.nxt):
                        m.d[self._domain] += self.stp.eq(1)
                m.d.comb += self.sink.ready.eq(self.nxt)

        with m.If(self.stp):
            m.d[self._domain] += self.stp.eq(0)

        # Receive
        with m.If(dir_r & self.dir):
            m.d[self._domain] += [
                self.source.valid.eq(1),
                self.source.data.eq(self.data.i),
                self.source.cmd.eq(~self.nxt)
            ]
        with m.Else():
            m.d[self._domain] += self.source.valid.eq(0)

        m.d.comb += self.source.last.eq(dir_r & ~self.dir)

        return m


class _Timer(Elaboratable):
    def __init__(self):
        self.cnt2us = Signal()
        self.cnt4ms = Signal()
        self.done   = Signal()

    def elaborate(self, platform):
        m = Module()

        counter = Signal(30)

        with m.If(self.cnt2us | self.cnt4ms):
            with m.If(self.done):
                m.d.ulpi += counter.eq(0)
            with m.Else():
                m.d.ulpi += counter.eq(counter + 1)
        with m.Else():
            m.d.ulpi += counter.eq(0)

        with m.If(self.cnt2us & (counter == int(60e6 * 2e-6))):
            m.d.comb += self.done.eq(1)
        with m.If(self.cnt4ms & (counter == int(60e6 * 4e-3))):
            m.d.comb += self.done.eq(1)

        return m


class _Splitter(Elaboratable):
    def __init__(self):
        self.sink   = stream.Endpoint([("data", 8), ("cmd", 1)])
        self.source = stream.Endpoint([("data", 8)])

    def elaborate(self, platform):
        sink = self.sink
        source = self.source

        m = Module()

        buf_data  = Signal(8)
        buf_valid = Signal()

        EVENT_MASK  = 0x30
        RX_INACTIVE = 0x00

        m.d.ulpi += source.valid.eq(0)

        # Separate RX CMD bytes from data bytes:
        # - RX CMD are dropped.
        # - Data bytes are forwarded through the source stream.
        # The last data byte is immediately followed by a RX CMD
        # with RXACTIVE field not set which allows us to delimit stream ends.
        with m.If(sink.valid):
            with m.If(~sink.cmd):
                m.d.ulpi += [
                    buf_data .eq(sink.data),
                    buf_valid.eq(1),
                ]
                with m.If(buf_valid):
                    m.d.ulpi += [
                        source.valid.eq(1),
                        source.data .eq(buf_data),
                        source.last .eq(0),
                    ]
            with m.Elif(sink.data & EVENT_MASK == RX_INACTIVE):
                with m.If(buf_valid):
                    m.d.ulpi += [
                        source.valid.eq(1),
                        source.last .eq(1),
                        source.data .eq(buf_data),
                        buf_valid   .eq(0),
                    ]

        return m


class _Sender(Elaboratable):
    def __init__(self):
        self.sink   = stream.Endpoint([("data", 8)])
        self.source = stream.Endpoint([("data", 8)])

    def elaborate(self, platform):
        sink = self.sink
        source = self.source

        m = Module()

        last_r = Signal(reset=1)

        # The first data byte needs to be handled separately:
        # - 4 MSB bytes are reserved and must be set to Transmit Command.
        # - 4 LSB bytes are PID, with 0 (NOPID) being an invalid value
        # that puts the ULPI PHY in an unstable state and sends crap:
        # it must be avoided.
        TRANSMIT = C(0b0100, 4)
        txd_cmd = Cat(sink.data[0:4], TRANSMIT)

        with m.If(sink.valid & sink.ready):
            m.d.ulpi += last_r.eq(sink.last)

        with m.If(last_r):
            m.d.comb += [
                source.data .eq(txd_cmd),
                source.valid.eq(sink.valid),
                source.last .eq(sink.last),
                sink  .ready.eq(source.ready),
            ]
        with m.Else():
            m.d.comb += sink.connect(source)

        return m

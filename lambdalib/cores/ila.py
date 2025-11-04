from amaranth import *  # type: ignore
from lambdalib.interface import stream
from lambdalib.cores.mem.stream import MemoryStream
from lambdalib.cores.serial import AsyncSerialTXStream

__all__ = ["ILA"]


class ILA(Elaboratable):
    """Integrated Logic Analyzer (ILA) for capturing and analyzing digital signals.

    This is a simple implementation of an Integrated Logic Analyzer (ILA).
    It captures data on a trigger signal and allows reading it out later via
    a serial interface at 115200 baud (or any other baudrate if specified).

    An accompagnying tool can be used to read the captured data from the serial
    port and generate a VCD file for waveform analysis:

        ila.py --depth 65536 --layout "data:8,valid:1,ready:1" \
               /dev/tty.usbserial-102 capture.vcd

    The ILA operates in four states:
    - IDLE: Waiting for a trigger signal
    - CAPTURE: Recording incoming data into memory
    - REWIND: Preparing to read out captured data
    - READOUT: Streaming captured data via serial interface

    Parameters:
        data_width: Width of the data bus to capture (in bits)
        depth: Number of samples to capture in memory
        sys_clk_freq: System clock frequency for serial baud rate calculation

    Attributes:
        data_in: Input signal to capture
        trigger: Signal to start data capture
        tx: Serial output for data readout
    """
    def __init__(self, data_width: int, depth: int, sys_clk_freq: int, baudrate: int = 115200):
        self._data_width = data_width
        self._depth = depth
        self._sys_clk_freq = sys_clk_freq
        self._baudrate = baudrate

        self.data_in = Signal(data_width)
        self.trigger = Signal()
        self.tx      = Signal()

    def elaborate(self, platform) -> Module:
        m = Module()

        # Calculate upper multiple of 8 for better data alignment
        aligned_width = ((self._data_width + 7) // 8) * 8
        
        m.submodules.mem = mem = MemoryStream(dw=aligned_width, depth=self._depth)
        
        # Pad input data to aligned width
        padded_data = Signal(aligned_width)
        m.d.comb += padded_data[:self._data_width].eq(self.data_in)
        m.d.comb += [
            mem.sink.data.eq(padded_data),
        ]
        
        m.submodules.downconverter = downconverter = stream._DownConverter(
            nbits_from=aligned_width,
            nbits_to=8,
            ratio=aligned_width // 8,
            reverse=False
        )

        m.submodules.tx = tx = AsyncSerialTXStream(
            o=self.tx,
            divisor=self._sys_clk_freq // self._baudrate,
        )
        m.d.comb += downconverter.source.connect(tx.sink)

        count = Signal(range(self._depth))

        with m.FSM():
            with m.State("IDLE"):
                m.d.sync += count.eq(0)

                with m.If(self.trigger):
                    m.d.comb += mem.sink.valid.eq(1)
                    m.d.sync += count.eq(count + 1)
                    m.next = "CAPTURE"

            with m.State("CAPTURE"):
                m.d.comb += mem.sink.valid.eq(1)
                m.d.sync += count.eq(count + 1)
                with m.If(count == self._depth - 1):
                    m.next = "REWIND"

            with m.State("REWIND"):
                m.d.comb += mem.rewind.eq(1)
                m.d.sync += count.eq(0)
                m.next = "READOUT"

            with m.State("READOUT"):
                m.d.comb += mem.source.connect(downconverter.sink)
                with m.If(mem.source.valid & downconverter.sink.ready):
                    m.d.sync += count.eq(count + 1)
                with m.If(count == self._depth - 1):
                    m.next = "STUCK"

            with m.State("STUCK"):
                pass

        return m

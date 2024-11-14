# 2024 - LambdaConcept - po@lambdaconcept.com

from amaranth import *

from ...interface import stream
from ...interface.stream_utils import *
from ..mem.stream import *


__all__ = ["SSD1306"]

SSD1306_I2C_ADDRESS         = 0x3C

SSD1306_SETLOWCOLUMN        = 0x00
SSD1306_SETHIGHCOLUMN       = 0x10
SSD1306_MEMORYMODE          = 0x20
SSD1306_COLUMNADDR          = 0x21
SSD1306_PAGEADDR            = 0x22
SSD1306_SETFADEOUT          = 0x23
SSD1306_SETSTARTLINE        = 0x40
SSD1306_SETCONTRAST         = 0x81
SSD1306_CHARGEPUMP          = 0x8D
SSD1306_SEGREMAP            = 0xA0
SSD1306_DISPLAYALLON_RESUME = 0xA4
SSD1306_DISPLAYALLON        = 0xA5
SSD1306_NORMALDISPLAY       = 0xA6
SSD1306_INVERTDISPLAY       = 0xA7
SSD1306_SETMULTIPLEX        = 0xA8
SSD1306_DISPLAYOFF          = 0xAE
SSD1306_DISPLAYON           = 0xAF
SSD1306_COMSCANINC          = 0xC0
SSD1306_COMSCANDEC          = 0xC8
SSD1306_SETDISPLAYOFFSET    = 0xD3
SSD1306_SETDISPLAYCLOCKDIV  = 0xD5
SSD1306_SETPRECHARGE        = 0xD9
SSD1306_SETCOMPINS          = 0xDA
SSD1306_SETVCOMDETECT       = 0xDB

class SSD1306(Elaboratable):
    """ Driver for SSD1306 based LCD screen.

    Connect the `source` stream to an I2CStream instance.
    Send `last` delimited framebuffer data to the `sink` stream.

    Parameters
    ----------
    width : int
        The screen width in pixels.
    height : int
        The screen height in pixels.
    burst_len : int
        Specify the maximum amount of framebuffer bytes that can be
        sent at a time before closing the I2C transaction.
        0 means unlimited.
    por_init : bool
        When True, the screen is automatically initialized upon power on reset.
        when False, the user need to assert `reset` for one clock cycle.
    """

    def __init__(self, width, height, burst_len=0, por_init=True):
        self.width = width
        self.height = height
        self.burst_len = burst_len
        self.por_init = por_init

        # Table from https://github.com/rm-hull/luma.oled/blob/main/luma/oled/device/__init__.py
        settings = {
            (128, 64): dict(clockdiv=0x80, compins=0x12, colstart=0),
            (128, 32): dict(clockdiv=0x80, compins=0x02, colstart=0),
            ( 96, 16): dict(clockdiv=0x60, compins=0x02, colstart=0),
            ( 64, 48): dict(clockdiv=0x80, compins=0x12, colstart=32),
            ( 64, 32): dict(clockdiv=0x80, compins=0x12, colstart=32),
        }.get((width, height))

        self._pages             = height // 8
        self._size              = width * self._pages
        self._multiplex         = height - 1
        self._displayclockdiv   = settings["clockdiv"]
        self._compins           = settings["compins"]
        self._colstart          = settings["colstart"]
        self._colend            = self._colstart + width

        if self.burst_len == 0:
            self.burst_len = self._size

        self.reset = Signal()
        self.ready = Signal()

        self.sink = stream.Endpoint([
            ("data", 8),
        ])
        # I2CStream interface
        self.source = stream.Endpoint([
            ("r_wn", 1),
            ("data", 8),
        ])
        self.error = Signal()

    def cmds_to_mem(self, cmds):
        mem = []

        for cmd in cmds:
            mem.append(SSD1306_I2C_ADDRESS << 1)    # Write
            mem.append(0x00)                        # Co = 0, D/C# = 0
            mem.append(cmd)

        return mem

    def elaborate(self, platform):
        sink = self.sink
        source = self.source

        m = Module()

        # Recipe for display initialization
        cmds = [
            SSD1306_DISPLAYOFF,
            SSD1306_SETDISPLAYCLOCKDIV,
            self._displayclockdiv,
            SSD1306_SETMULTIPLEX,
            self._multiplex,
            SSD1306_SETDISPLAYOFFSET,
            0x0,                            # No offset
            SSD1306_SETSTARTLINE | 0x0,     # Line 0
            SSD1306_CHARGEPUMP,
            0x14,                           # Enable Charge Pump
            SSD1306_MEMORYMODE,
            0x00,                           # Page addressing mode
            SSD1306_SEGREMAP | 0x1,
            SSD1306_COMSCANDEC,
            SSD1306_SETCOMPINS,
            self._compins,
            SSD1306_SETCONTRAST,
            0x7F,
            SSD1306_SETPRECHARGE,
            0xF1,
            SSD1306_SETVCOMDETECT,
            0x40,
            SSD1306_DISPLAYALLON_RESUME,
            SSD1306_NORMALDISPLAY,
            SSD1306_DISPLAYON,
        ]
        blob = self.cmds_to_mem(cmds)

        m.submodules.init = init = \
                LastInserter(3)(MemoryStreamReader(8, blob))

        # Recipe for sending a framebuffer
        cmds = [
            SSD1306_COLUMNADDR,
            self._colstart,                # Column start address. (0 = reset)
            self._colend - 1,              # Column end address.
            SSD1306_PAGEADDR,
            0,                             # Page start address. (0 = reset)
            self._pages - 1,               # Page end address.
        ]
        blob = self.cmds_to_mem(cmds)

        m.submodules.display = display = \
                LastInserter(3)(MemoryStreamReader(8, blob))

        cnt = Signal(range(self.burst_len + 2))

        with m.FSM():
            with m.State("UNKNOWN"):
                with m.If(self.reset | self.por_init):
                    m.next = "RESET"

            with m.State("RESET"):
                m.d.comb += [
                    init   .rewind.eq(1),
                    display.rewind.eq(1),
                ]
                m.d.sync += self.ready.eq(0)
                m.next = "INIT"

            with m.State("INIT"):
                # Send the appropriate sequence to power on
                # and initialize the display.
                m.d.comb += [
                    init.source.connect(source),
                    source.r_wn.eq(0),  # Write only
                ]
                with m.If(init.done & ~source.valid):
                    m.next = "DISPLAY"

            with m.State("DISPLAY"):
                with m.If(self.reset):
                    m.next = "RESET"

                # Send the appropriate sequence to prepare
                # for a frame buffer write.
                with m.Elif(sink.valid): # ~sink.ready
                    m.d.comb += [
                        display.source.connect(source),
                        source.r_wn.eq(0),  # Write only
                    ]
                    with m.If(display.done & ~source.valid):
                        # On the first time after initialization
                        # we want to clear the frame buffer to make
                        # sure we do not display crap.
                        # with m.If(~self.ready):
                        #     m.next = "CLEAR"
                        # with m.Else():
                        m.next = "FRAMEBUFFER"

            with m.State("FRAMEBUFFER"):
                m.d.comb += [
                    source.r_wn.eq(0),
                    source.last.eq((cnt == self.burst_len+2-1) | sink.last),
                ]

                # Send the I2C address and control byte,
                # then send the frame buffer data up to burst length.
                with m.If(cnt == 0):
                    m.d.comb += [
                        source.data .eq(SSD1306_I2C_ADDRESS << 1),
                        source.valid.eq(1),
                    ]
                with m.Elif(cnt == 1):
                    m.d.comb += [
                        source.data .eq(0x40),  # Control byte: Co = 0, D/C# = 1
                        source.valid.eq(1),
                    ]
                with m.Else():
                    m.d.comb += [
                        source.data .eq(sink.data),
                        source.valid.eq(sink.valid),
                        sink  .ready.eq(source.ready),
                    ]

                # End of burst detection
                # Reset the counter and stay in this state
                #   to send the next burst, or go back to the
                #   DISPLAY state when the end of the framebuffer is reached.
                with m.If(source.valid & source.ready):
                    with m.If(~source.last):
                        m.d.sync += cnt.eq(cnt + 1)
                    with m.Else():
                        m.d.sync += cnt.eq(0)
                        with m.If(sink.last):
                            m.d.comb += display.rewind.eq(1)
                            m.next = "DISPLAY"

        return m

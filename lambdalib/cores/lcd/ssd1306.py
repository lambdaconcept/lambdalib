# 2024 - LambdaConcept - po@lambdaconcept.com

from amaranth import *

from ...interface import stream
from ...interface.stream_utils import *
from ..mem.stream import *
from ..i2c.stream import *


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


class SSD1306_Wrapper(Elaboratable):
    def __init__(self):
        self.sink = stream.Endpoint([
            ("d_cn", 1),
            ("data", 8),
        ])
        self.source = stream.Endpoint(i2c_stream_description)
        self.i2c_error = Signal()

    def elaborate(self, platform):
        sink = self.sink
        source = self.source

        m = Module()

        m.d.comb += source.r_wn.eq(0)   # Write only

        with m.FSM():
            # Send the I2C address and control byte
            with m.State("ADDR"):
                m.d.comb += [
                    source.data .eq(SSD1306_I2C_ADDRESS << 1),
                    source.valid.eq(sink.valid),
                ]
                with m.If(source.valid & source.ready):
                    with m.If(self.i2c_error):
                        m.next = "ERROR"
                    with m.Else():
                        m.next = "CONTROL"

            with m.State("CONTROL"):
                m.d.comb += [
                    # Control byte:
                    # Command: 0x00: Co = 0, D/C# = 0
                    # Data:    0x40: Co = 0, D/C# = 1
                    source.data .eq(Mux(sink.d_cn, 0x40, 0x00)),
                    source.valid.eq(sink.valid),
                ]
                with m.If(source.valid & source.ready):
                    m.next = "DATA"

            with m.State("DATA"):
                m.d.comb += [
                    source.data. eq(sink.data),
                    source.valid.eq(sink.valid),
                    source.last .eq(sink.last),
                    sink  .ready.eq(source.ready),
                ]
                with m.If(source.valid & source.ready & source.last):
                    m.next = "ADDR"

            with m.State("ERROR"):
                # The I2C target device is not present on the bus (NAK)
                # drop the sink until `last`.
                m.d.comb += sink.ready.eq(1)
                with m.If(sink.valid & sink.last):
                    m.next = "ADDR"

        return m


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
    por_init : bool
        When True, the screen is automatically initialized upon power on reset.
        when False, the user need to assert `reset` for one clock cycle.
    """

    def __init__(self, width, height, por_init=True):
        self.width = width
        self.height = height
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

        self.reset = Signal()
        self.ready = Signal()

        self.sink   = stream.Endpoint([("data", 8)])
        self.source = stream.Endpoint(i2c_stream_description)
        self.i2c_error = Signal()

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
        m.submodules.init = init = MemoryStreamReader(8, cmds)

        # Recipe for sending a framebuffer
        cmds = [
            SSD1306_COLUMNADDR,
            self._colstart,                # Column start address. (0 = reset)
            self._colend - 1,              # Column end address.
            SSD1306_PAGEADDR,
            0,                             # Page start address. (0 = reset)
            self._pages - 1,               # Page end address.
        ]
        m.submodules.display = display = MemoryStreamReader(8, cmds)

        # Instanciate the I2C address and control byte wrapper
        m.submodules.wrapper = wrapper = SSD1306_Wrapper()
        m.d.comb += wrapper.source.connect(source)
        m.d.comb += wrapper.i2c_error.eq(self.i2c_error)

        cnt = Signal(range(self._size))

        with m.FSM():
            with m.State("UNKNOWN"):
                with m.If(self.reset | self.por_init):
                    m.d.sync += self.ready.eq(0)
                    m.next = "RESET"

            with m.State("RESET"):
                m.d.comb += [
                    init   .rewind.eq(1),
                    display.rewind.eq(1),
                ]
                m.next = "INIT"

            with m.State("INIT"):
                # Send the appropriate sequence to power on
                # and initialize the display.
                m.d.comb += [
                    init.source.connect(wrapper.sink, exclude={"last"}),
                    wrapper.sink.d_cn.eq(0),        # Commands
                    wrapper.sink.last.eq(1),
                ]
                with m.If(init.done & ~init.source.valid):
                    m.next = "DISPLAY"

            with m.State("DISPLAY"):
                with m.If(self.reset):
                    m.d.sync += self.ready.eq(0)
                    m.next = "RESET"

                # Send the appropriate sequence to prepare
                # for a frame buffer write.
                with m.Elif(~self.ready | sink.valid):
                    m.d.comb += [
                        display.source.connect(wrapper.sink, exclude={"last"}),
                        wrapper.sink.d_cn.eq(0),    # Commands
                        wrapper.sink.last.eq(1),
                    ]
                    with m.If(display.done & ~display.source.valid):
                        m.next = "FRAMEBUFFER"

            with m.State("FRAMEBUFFER"):
                # On the first time after initialization
                # we want to clear the frame buffer to make
                # sure we do not display crap.
                with m.If(~self.ready):
                    m.d.comb += [
                        wrapper.sink.valid.eq(1),
                        wrapper.sink.data .eq(0),       # Black pixels
                        wrapper.sink.last .eq((cnt == self._size-1)),
                    ]
                with m.Else():
                    m.d.comb += [
                        wrapper.sink.valid.eq(sink.valid),
                        wrapper.sink.data .eq(sink.data),
                        wrapper.sink.last .eq((cnt == self._size-1) | sink.last),
                        sink.ready        .eq(wrapper.sink.ready),
                    ]
                m.d.comb += wrapper.sink.d_cn .eq(1)    # Framebuffer data

                with m.If(wrapper.sink.valid & wrapper.sink.ready):
                    with m.If(~wrapper.sink.last):
                        m.d.sync += cnt.eq(cnt + 1)
                    with m.Else():
                        m.d.sync += cnt.eq(0)
                        m.d.sync += self.ready.eq(1)
                        m.d.comb += display.rewind.eq(1)
                        m.next = "DISPLAY"

        return m

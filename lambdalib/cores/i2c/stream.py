# 2022 - LambdaConcept - po@lambdaconcept.com

from amaranth import *

from ...interface import stream
from .i2c import *


__all__ = [
    "I2CStream",
    "I2CWriterStream",
    "I2CRegStream",
    "i2c_stream_description",
    "i2c_writer_description",
]


i2c_stream_description = [
    ("r_wn", 1),
    ("data", 8),
]
i2c_writer_description = [
    ("data", 8),
]


class I2CStage:
    ADDR_DEV = 0
    ADDR_REG = 1
    DATA_REG = 2
i2c_stage_dw = range(I2CStage.DATA_REG + 1)


class I2CStream(Elaboratable):
    """ Bidirectional stream wrapper for I2C.

    Sink stream description:
        `r_wn`: 1 == read 8 bits on SDA
                0 == write 8 bits on SDA
        `data`: for write: data to write on SDA
                for read: N/A
        `last`: 1 to indicate this is the last I2C transfer,
                I2C stop will be sent at the end of this transaction.

    Source stream description:
        `data`: for read: 8 bits read from SDA
                for write: N/A
        `last`: for read: indicate this was the last data read
                before the end of the I2C transaction.

    Example of use: I2C 8bit address register write
    ===============================================

        Step 1: Write I2C chip address
            r_wn == 0
            data == I2C chip address << 1
            last == 0

        Step 2: Write register address
            r_wn == 0
            data == register address
            last == 0

        Step 3: Write register values
            r_wn == 0
            data == 1st register value
            last == 0

            [...]

            r_wn == 0
            data == nth register value
            last == 1   <--- I2C STOP

    Example of use: I2C 8bit address register read
    ==============================================

        Step 1: Write I2C chip address
            r_wn == 0
            data == I2C chip address << 1
            last == 0

        Step 2: Write register address
            r_wn == 0
            data == register address
            last == 1   <--- I2C STOP

        Step 3: Write I2C chip address
            r_wn == 0
            data == (I2C chip address << 1) | 1
            last == 0

        Step 4: Read register values
            sink.r_wn == 1
            sink.data == N/A
            sink.last == 0

            source.data == 1st register value
            source.last == 0

            [...]

            sink.r_wn == 1
            sink.data == N/A
            sink.last == 1   <--- I2C STOP

            source.data == nth register value
            source.last == 1
    """

    def __init__(self, pins, period_cyc, **kwargs):
        self.pins = pins
        self.period_cyc = period_cyc
        self.kwargs = kwargs

        self.error  = Signal()
        self.sink   = stream.Endpoint(i2c_stream_description)
        self.source = stream.Endpoint([
            ("data", 8),
        ])

    def elaborate(self, platform):
        sink = self.sink
        source = self.source

        m = Module()

        i2c = I2CInitiator(self.pins, self.period_cyc, **self.kwargs)
        m.submodules.i2c = i2c

        last_r = Signal()

        # Drive the i2c core
        with m.FSM():

            with m.State("IDLE"):
                with m.If(~i2c.busy):
                    with m.If(sink.valid):
                        m.next = "START"

            with m.State("START"):
                m.d.comb += i2c.start.eq(1)
                m.next = "_WAIT_START"

            with m.State("_WAIT_START"):
                with m.If(~i2c.busy):
                    m.next = "XFER"

            with m.State("XFER"):
                m.d.sync += last_r.eq(sink.last)

                with m.If(sink.valid):
                    # Read
                    with m.If(sink.r_wn):
                        m.d.comb += [
                            i2c.read.eq(1),
                            i2c.ack_i.eq(~sink.last),
                        ]
                        m.d.comb += sink.ready.eq(1)
                        m.next = "_WAIT_READ"

                    # Write
                    with m.Else():
                        m.d.comb += [
                            i2c.write.eq(1),
                            i2c.data_i.eq(sink.data),
                        ]
                        m.next = "_WAIT_WRITE"

            with m.State("_WAIT_WRITE"):
                with m.If(~i2c.busy):
                    m.d.comb += sink.ready.eq(1)

                    # We were NAKed
                    with m.If(~i2c.ack_o):
                        m.d.comb += self.error.eq(1)
                        m.next = "STOP"

                    # We were ACKed
                    with m.Else():

                        with m.If(last_r):
                            m.next = "STOP"
                        with m.Else():
                            m.next = "XFER"

            with m.State("_WAIT_READ"):
                with m.If(~i2c.busy):
                    m.d.comb += [
                        source.data.eq(i2c.data_o),
                        source.valid.eq(1),
                        source.last.eq(last_r),
                    ]
                    with m.If(source.ready):

                        with m.If(last_r):
                            m.next = "STOP"
                        with m.Else():
                            m.next = "XFER"

            with m.State("STOP"):
                m.d.comb += i2c.stop.eq(1)
                m.next = "_WAIT_STOP"

            with m.State("_WAIT_STOP"):
                with m.If(~i2c.busy):
                    m.next = "IDLE"

        return m


class I2CWriterStream(Elaboratable):
    """ Write only stream wrapper around I2CInitiator.

    Important note:
        This module is intented to be used only
        when I2C transactions always have the same 3 steps format:
            1. I2C chip address
            2. register address
            3. register value

        The `sink.last` signal is not used and I2C transaction is
        always stopped on the 3rd step after writing one register value.

        As such, this module cannot be used to write a burst of registers.
    """
    def __init__(self, pins, period_cyc, **kwargs):
        self.pins = pins
        self.period_cyc = period_cyc
        self.kwargs = kwargs

        self.sink = stream.Endpoint(i2c_writer_description)

    def elaborate(self, platform):
        sink = self.sink

        m = Module()

        i2c = I2CInitiator(self.pins, self.period_cyc, **self.kwargs)
        m.submodules.i2c = i2c

        stage = Signal(i2c_stage_dw)
        retry = Signal()
        cache = [Signal.like(sink.data) for i in i2c_stage_dw]
        cache_stage = Signal.like(stage)

        # When we need to retry a previously NAKed transaction, we drive
        # the i2c data from the previously stored values.
        # If we no longer have valid cached values, we fallback to the stream.
        use_data_from_cache = (retry & (cache_stage >= stage))

        with m.If(use_data_from_cache):
            with m.Switch(stage):
                for i in i2c_stage_dw:
                    with m.Case(i):
                        m.d.comb += i2c.data_i.eq(cache[i])

        # Not retrying or no more data available in the cache:
        # drive the i2c data from the sink stream. We still want
        # to store the values for later use in case we get NAK.
        with m.Else():
            m.d.comb += i2c.data_i.eq(sink.data)
            with m.If(i2c.write):
                m.d.comb += sink.ready.eq(1)

                m.d.sync += cache_stage.eq(stage)
                with m.Switch(stage):
                    for i in i2c_stage_dw:
                        with m.Case(i):
                            m.d.sync += cache[i].eq(sink.data)

        # Drive the i2c core
        with m.FSM():

            with m.State("IDLE"):
                with m.If(~i2c.busy):
                    with m.If(sink.valid | use_data_from_cache):
                        m.d.sync += stage.eq(I2CStage.ADDR_DEV)
                        m.next = "START"

            with m.State("START"):
                m.d.comb += i2c.start.eq(1)
                m.next = "_WAIT_START"

            with m.State("_WAIT_START"):
                with m.If(~i2c.busy):
                    m.next = "WRITE"

            with m.State("WRITE"):
                m.d.comb += i2c.write.eq(1)
                m.d.sync += stage.eq(stage + 1)
                m.next = "_WAIT_WRITE"

            with m.State("_WAIT_WRITE"):
                with m.If(~i2c.busy):
                    with m.If(~i2c.ack_o):
                        # We were NAKed, stop and retry the transaction
                        # from the beginning.
                        m.d.sync += retry.eq(1)
                        m.next = "STOP"
                        # XXX implement a maximum retry timeout ??

                    with m.Else():
                        # We were ACKed, continue with the next data
                        # or stop when reaching the end of the transaction.
                        with m.If(stage > I2CStage.DATA_REG):
                            m.d.sync += retry.eq(0)
                            m.next = "STOP"

                        with m.Elif(sink.valid | use_data_from_cache):
                            m.next = "WRITE"

            with m.State("STOP"):
                m.d.comb += i2c.stop.eq(1)
                m.next = "_WAIT_STOP"

            with m.State("_WAIT_STOP"):
                with m.If(~i2c.busy):
                    m.next = "IDLE"

        return m


class I2CRegStream(Elaboratable):
    """Converts addr/val stream into an I2C stream.
    Currently only supports 8bit reg addresses and values."""
    def __init__(self, i2c_addr, addr_width=8, val_width=8):
        assert addr_width == 8
        assert val_width == 8

        self._i2c_addr = i2c_addr
        self._addr_width = addr_width
        self._val_width = val_width

        self.sink = stream.Endpoint([
            ("addr", addr_width),
            ("val", val_width)
        ])
        self.source = stream.Endpoint([
            ("data", 8),
        ])

    def elaborate(self, platform):
        m = Module()

        # Latch addr/val
        addr_d = Signal(self._addr_width)
        val_d = Signal(self._val_width)

        with m.FSM():
            with m.State("IDLE"):
                m.d.comb += self.sink.ready.eq(1)
                with m.If(self.sink.valid):
                    m.d.sync += [
                        self.source.valid.eq(1),
                        self.source.data.eq(self._i2c_addr << 1),
                        addr_d.eq(self.sink.addr),
                        val_d.eq(self.sink.val),
                    ]
                    m.next = "PUSH-SLAVE-ADDR"
            
            with m.State("PUSH-SLAVE-ADDR"):
                with m.If(self.source.ready):
                    m.d.sync += self.source.data.eq(addr_d)
                    m.next = "PUSH-REG-ADDR"

            with m.State("PUSH-REG-ADDR"):
                with m.If(self.source.ready):
                    m.d.sync += [
                        self.source.data.eq(val_d),
                        self.source.last.eq(1),
                    ]
                    m.next = "PUSH-REG-VAL"

            with m.State("PUSH-REG-VAL"):
                with m.If(self.source.ready):
                    m.d.sync += [
                        self.source.valid.eq(0),
                        self.source.last.eq(0),
                    ]
                    m.next = "IDLE"

        return m

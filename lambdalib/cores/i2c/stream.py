# 2022 - LambdaConcept - po@lambdaconcept.com

from amaranth import *

from ...interface import stream
from .i2c import *


__all__ = [
    "I2CStream",
    "I2CWriterStream",
    "I2CRegStream",
    "i2c_writer_description",
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
    def __init__(self, pins, period_cyc, **kwargs):
        self.pins = pins
        self.period_cyc = period_cyc
        self.kwargs = kwargs

        self.error = Signal()
        self.sink = stream.Endpoint([
            ("r_wn", 1),
            ("data", 8),
        ])
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
    """Converts addr/val stream into an I2C stream."""
    def __init__(self, i2c_addr, addr_width=8, val_width=8):
        if addr_width % 8 != 0 and addr_width > 0:
            raise ValueError("addr_width must be a multiple of 8 bits")
        if val_width % 8 != 0 and val_width > 0:
            raise ValueError("val_width must be a multiple of 8 bits")

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
        addr_latch = Signal(self._addr_width)
        val_latch = Signal(self._val_width)
        byte_pos = Signal(range(max(self._addr_width // 8, self._val_width // 8)))

        with m.FSM():
            with m.State("IDLE"):
                m.d.comb += self.sink.ready.eq(1)
                with m.If(self.sink.valid):
                    m.d.sync += [
                        self.source.valid.eq(1),
                        self.source.data.eq(self._i2c_addr << 1),
                        addr_latch.eq(self.sink.addr),
                        val_latch.eq(self.sink.val),
                        byte_pos.eq(self._addr_width // 8 - 1),
                    ]
                    m.next = "PUSH-SLAVE-ADDR"
            
            with m.State("PUSH-SLAVE-ADDR"):
                with m.If(self.source.ready):
                    m.d.sync += [
                        self.source.data.eq(addr_latch.word_select(byte_pos.as_unsigned(), 8)),
                    ]
                    m.next = "PUSH-REG-ADDR"

            with m.State("PUSH-REG-ADDR"):
                with m.If(self.source.ready):
                    with m.If(byte_pos > 0):
                        m.d.sync += [
                            self.source.data.eq(addr_latch.word_select((byte_pos - 1).as_unsigned(), 8)),
                            byte_pos.eq(byte_pos - 1),
                        ]
                    with m.Else():
                        m.d.sync += [
                            self.source.data.eq(val_latch[-8:]),
                            byte_pos.eq(self._val_width // 8 - 1),
                        ]
                        if self._val_width == 8:
                            m.d.sync += self.source.last.eq(1)
                        m.next = "PUSH-REG-VAL"

            with m.State("PUSH-REG-VAL"):
                with m.If(self.source.ready):
                    with m.If(byte_pos == 0):
                        m.d.sync += [
                            self.source.valid.eq(0),
                            self.source.last.eq(0),
                        ]
                        m.next = "IDLE"
                    with m.Else():
                        m.d.sync += [
                            self.source.data.eq(val_latch.word_select((byte_pos - 1).as_unsigned(), 8)),
                            byte_pos.eq(byte_pos - 1),
                        ]
                        with m.If(byte_pos == 1):
                            m.d.sync += self.source.last.eq(1)

        return m

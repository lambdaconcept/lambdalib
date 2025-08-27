# Endless potentiometer decoding into relative rotation
# 2025 - LambdaConcept <contact@lambdaconcept.com>
from amaranth import *
from ...interface import stream

__all__ = ["EndlessPotentiometerDecoder"]


class _ThresholdDetector(Elaboratable):
    """Detects when a value changes above/below a threshold"""
    def __init__(self, width, threshold, id_width=0):
        self._width = width
        self._threshold = threshold

        self.readout = stream.Endpoint([
            ("id", id_width),
            ("value", width),
            ("previous_value", width),
        ])

        self.detection = stream.Endpoint([
            ("id", id_width),
            ("up", 1),
            ("down", 1),
            ("value", width),  # Readout value passthrough
            ("delta", signed(width + 1)),  # value - previous_value
        ])

    def elaborate(self, platform):
        m = Module()

        low_threshold = Signal(signed(self._width + 1))
        high_threshold = Signal(signed(self._width + 1))
        m.d.comb += [
            low_threshold.eq(self.readout.previous_value - self._threshold),
            high_threshold.eq(self.readout.previous_value + self._threshold),
        ]

        with m.If(self.detection.ready | ~self.detection.valid):
            m.d.sync += [
                self.detection.valid.eq(self.readout.valid),
                self.detection.up.eq(self.readout.value > high_threshold),
                self.detection.down.eq(self.readout.value < low_threshold),
                self.detection.value.eq(self.readout.value),
                self.detection.delta.eq(self.readout.value - self.readout.previous_value),
                self.detection.id.eq(self.readout.id),
            ]
        m.d.comb += self.readout.ready.eq(self.detection.ready | ~self.detection.valid)

        return m


class _DirectionDecoding(Elaboratable):
    def __init__(self, width, id_width=0):
        self._width = width

        self.dir_a = stream.Endpoint([
            ("id", id_width),
            ("up", 1),
            ("down", 1),
            ("value", width),
            ("delta", signed(width + 1)),
        ])
        self.dir_b = stream.Endpoint([
            ("id", id_width),
            ("up", 1),
            ("down", 1),
            ("value", width),
            ("delta", signed(width + 1)),
        ])

        self.direction = stream.Endpoint([
            ("id", id_width),
            ("clockwise", 1),
            ("counterclockwise", 1),
            ("value_a", width),
            ("delta_a", signed(width + 1)),
            ("value_b", width),
            ("delta_b", signed(width + 1)),
        ])

    def elaborate(self, platform):
        m = Module()

        m.d.comb += [
            self.dir_a.ready.eq(self.direction.ready & self.dir_b.valid),
            self.dir_b.ready.eq(self.direction.ready & self.dir_a.valid),
        ]

        with m.If(self.direction.ready | ~self.direction.valid):
            m.d.sync += [
                self.direction.valid.eq(self.dir_a.valid & self.dir_b.valid),
                self.direction.value_a.eq(self.dir_a.value),
                self.direction.value_b.eq(self.dir_b.value),
                self.direction.delta_a.eq(self.dir_a.delta),
                self.direction.delta_b.eq(self.dir_b.delta),
            ]

        a_above_b = Signal()
        a_above_mid = Signal()
        b_above_mid = Signal()
        m.d.comb += [
            a_above_b.eq(self.dir_a.value > self.dir_b.value),
            a_above_mid.eq(self.dir_a.value > (1 << self._width) // 2),
            b_above_mid.eq(self.dir_b.value > (1 << self._width) // 2),
        ]

        with m.If(self.direction.ready | ~self.direction.valid):
            with m.If(self.dir_a.down & self.dir_b.down):
                with m.If(a_above_b):
                    m.d.sync += self.direction.clockwise.eq(1)
                with m.Else():
                    m.d.sync += self.direction.counterclockwise.eq(1)
            with m.Elif(self.dir_a.up & self.dir_b.up):
                with m.If(~a_above_b):
                    m.d.sync += self.direction.clockwise.eq(1)
                with m.Else():
                    m.d.sync += self.direction.counterclockwise.eq(1)
            with m.Elif(self.dir_a.up & self.dir_b.down):
                with m.If(a_above_mid | b_above_mid):
                    m.d.sync += self.direction.clockwise.eq(1)
                with m.Else():
                    m.d.sync += self.direction.counterclockwise.eq(1)
            with m.Elif(self.dir_a.down & self.dir_b.up):
                with m.If(~a_above_mid | ~b_above_mid):
                    m.d.sync += self.direction.clockwise.eq(1)
                with m.Else():
                    m.d.sync += self.direction.counterclockwise.eq(1)
            with m.Else():
                m.d.sync += [
                    self.direction.clockwise.eq(0),
                    self.direction.counterclockwise.eq(0),
                ]

        return m


class _ReadoutDeadzoneMuxer(Elaboratable):
    def __init__(self, width, deadzone=0.8, id_width=0):
        self._width = width
        self._deadzone = deadzone

        self.direction = stream.Endpoint([
            ("id", id_width),
            ("clockwise", 1),
            ("counterclockwise", 1),
            ("value_a", width),
            ("delta_a", signed(width + 1)),
            ("value_b", width),
            ("delta_b", signed(width + 1)),
        ])

        self.position = stream.Endpoint([
            ("id", id_width),
            ("diff", signed(width + 1)),
            ("value_a", width),
            ("value_b", width),
        ])

    def elaborate(self, platform):
        m = Module()

        deadzone_max = int((1 << self._width) * self._deadzone)
        deadzone_min = int((1 << self._width) * (1 - self._deadzone))

        value = Signal(signed(self._width + 1))
        with m.If((self.direction.value_a < deadzone_max) & (self.direction.value_a > deadzone_min)):
            with m.If(self.direction.clockwise):
                m.d.comb += value.eq(abs(self.direction.delta_a))
            with m.Elif(self.direction.counterclockwise):
                m.d.comb += value.eq(-abs(self.direction.delta_a))
            with m.Else():
                m.d.comb += value.eq(0)
        with m.Else():
            with m.If(self.direction.clockwise):
                m.d.comb += value.eq(abs(self.direction.delta_b))
            with m.Elif(self.direction.counterclockwise):
                m.d.comb += value.eq(-abs(self.direction.delta_b))
            with m.Else():
                m.d.comb += value.eq(0)

        with m.If(self.position.ready | ~self.position.valid):
            m.d.sync += [
                self.position.valid.eq(self.direction.valid),
                self.position.value_a.eq(self.direction.value_a),
                self.position.value_b.eq(self.direction.value_b),
                self.position.diff.eq(value),
                self.position.id.eq(self.direction.id),
            ]
        m.d.comb += self.direction.ready.eq(self.position.ready | ~self.position.valid)

        return m


class EndlessPotentiometerDecoder(Elaboratable):
    def __init__(self, width, threshold, deadzone, id_width=0):
        self._width = width
        self._threshold = threshold
        self._deadzone = deadzone
        self._id_width = id_width

        self.adc_readout = stream.Endpoint([
            ("id", id_width),
            ("value_a", width),
            ("previous_value_a", width),
            ("value_b", width),
            ("previous_value_b", width),
        ])

        self.position = stream.Endpoint([
            ("id", id_width),
            ("diff", signed(width + 1)),
            ("value_a", width),
            ("value_b", width),
        ])

    def elaborate(self, platform):
        m = Module()

        m.submodules.thres_det_a = thres_det_a = _ThresholdDetector(self._width, self._threshold, self._id_width)
        m.submodules.thres_det_b = thres_det_b = _ThresholdDetector(self._width, self._threshold, self._id_width)
        m.submodules.dir_decoding = dir_decoding = _DirectionDecoding(self._width, self._id_width)
        m.submodules.deadzone_mux = deadzone_mux = _ReadoutDeadzoneMuxer(self._width, self._deadzone, self._id_width)
        m.d.comb += [
            self.adc_readout.ready.eq(thres_det_a.readout.ready & thres_det_b.readout.ready),

            thres_det_a.readout.valid.eq(self.adc_readout.valid & thres_det_b.readout.ready),
            thres_det_a.readout.id.eq(self.adc_readout.id),
            thres_det_a.readout.value.eq(self.adc_readout.value_a),
            thres_det_a.readout.previous_value.eq(self.adc_readout.previous_value_a),
            thres_det_b.readout.valid.eq(self.adc_readout.valid & thres_det_a.readout.ready),
            thres_det_b.readout.id.eq(self.adc_readout.id),
            thres_det_b.readout.value.eq(self.adc_readout.value_b),
            thres_det_b.readout.previous_value.eq(self.adc_readout.previous_value_b),

            thres_det_a.detection.connect(dir_decoding.dir_a),
            thres_det_b.detection.connect(dir_decoding.dir_b),

            dir_decoding.direction.connect(deadzone_mux.direction),
            deadzone_mux.position.connect(self.position),
        ]

        return m

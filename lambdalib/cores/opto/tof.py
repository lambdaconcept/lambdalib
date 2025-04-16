"""Time-of-flight related cores"""

from amaranth import *

from lambdalib.cores.i2c.stream import I2CStream
from lambdalib.interface.stream import Endpoint
from lambdalib.time.timer import WaitTimer


__all__ = ["VL6180XPoller"]


class VL6180XPoller(Elaboratable):
    def __init__(self, pins, sys_freq, i2c_freq=400e6, poll_freq=1e3):
        self._pins = pins
        self._sys_freq = sys_freq
        self._i2c_freq = i2c_freq
        self._poll_freq = poll_freq

        self.samples = stream.Endpoint([("data", 8)])

    def elaborate(self, platform):
        m = Module()

        m.submodules.i2c = i2c = I2CStream(
            pins=self._pins,
            period_cyc=self._sys_freq / self._i2c_freq,
        )

        # Power up timer
        m.submodules.pup_timer = pup_timer = WaitTimer(self._sys_freq * 1.4e-3)  # 1.4ms delay (Power-Up Delay + Boot time)

        # Polling pulse generator
        polling_interval_cycles = self._sys_freq / self._poll_freq
        polling_cnt = Signal(range(polling_interval_cycles))
        with m.If(polling_cnt == 0):
            m.d.sync += polling_cnt.eq(polling_interval_cycles - 1)
        with m.Else():
            m.d.sync += polling_cnt.eq(polling_cnt - 1)

        # Routine from Fig 11/Fig 12 of VL6180X datasheet
        with m.FSM():
            with m.State("POWER-UP"):
                with m.If(pup_timer.done):
                    m.next = "WAIT-DEVICE-BOOTED"

            with m.State("INIT-DATA"):
                pass

            with m.State("PREPARE"):
                pass

            with m.State("WAIT-POLLING-PULSE"):
                with m.If(polling_cnt == 0):
                    m.next = "RANGE-POLL"

            with m.State("RANGE-POLL"):
                pass

        return m

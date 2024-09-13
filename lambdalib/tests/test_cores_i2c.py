# 2022 - LambdaConcept - po@lambdaconcept.com

from amaranth import *
from amaranth.lib.io import Pin

from lambdalib.cores.i2c.stream import *
from lambdalib.cores.i2c.proto import *

from amaranth.sim import *
from lambdalib.interface.stream_sim import *


class I2C_Pins_Stub:
    def __init__(self):
        self.scl = Pin(1, dir="io")
        self.sda = Pin(1, dir="io")

    def sync_process(self):
        yield Passive()
        while True:
            yield self.scl.i.eq(self.scl.o)
            yield self.sda.i.eq(self.sda.o)
            yield


def test_i2c_stream_writer():
    pins = I2C_Pins_Stub()
    dut = I2CWriterStream(pins, 100, clk_stretch=False)
    sim = Simulator(dut)

    chipaddr = (0x69 << 1)
    datas = {
        "data": [
            chipaddr,   0xc3,   0xa5,
            chipaddr,   0xd2,   0x18,
        ],
    }

    sender = StreamSimSender(dut.sink, datas, speed=0.9, verbose=True)

    sim.add_clock(1e-6)
    sim.add_sync_process(sender.sync_process)
    sim.add_sync_process(pins.sync_process)
    with sim.write_vcd("tests/test_i2c_stream_writer.vcd"):
        sim.run()


def test_i2c_stream():
    pins = I2C_Pins_Stub()
    dut = I2CStream(pins, 100, clk_stretch=False)
    sim = Simulator(dut)

    datas = {
        "data": [ 0b10010000, 0b00000001, 0b10000100, 0b10000011,
                  0b10010000, 0b00000000,
                  0b10010001, 0b00000000, 0b00000000,
        ],
        "r_wn": [          0,          0,          0,          0,
                           0,          0,
                           0,          1,          1,
        ],
        "last": [          0,          0,          0,          1,
                           0,          1,
                           0,          0,          1,
        ],
    }

    sender = StreamSimSender(dut.sink, datas, speed=0.9, verbose=True)
    receiver = StreamSimReceiver(dut.source, length=2, speed=1, verbose=True)

    sim.add_clock(1e-6)
    sim.add_sync_process(sender.sync_process)
    sim.add_sync_process(receiver.sync_process)
    sim.add_sync_process(pins.sync_process)
    with sim.write_vcd("tests/test_i2c_stream.vcd"):
        sim.run()


def test_i2c_proto():
    pins = I2C_Pins_Stub()
    dut = I2CProto(100e6, i2c_pins=pins, i2c_freq=400e3, clk_stretch=False)
    sim = Simulator(dut)

    datas = {
        "data": [(0x69 << 1) | 0, 0x00,
                 (0x69 << 1) | 0, 0x02, 0x0F, 0x04,
                 (0x69 << 1) | 0, 0x01, 0x0F,
                 (0x69 << 1) | 1, 0x03,
        ],
    }
    r_len = 1 + 1 + 1 + 1 + 3

    sender = StreamSimSender(dut.sink, datas, speed=0.9,
                             verbose=True, strname="sender")
    receiver = StreamSimReceiver(dut.source, length=r_len, speed=1,
                                 verbose=True, strname="receiver")

    sim.add_clock(1e-6)
    sim.add_sync_process(sender.sync_process)
    sim.add_sync_process(receiver.sync_process)
    sim.add_sync_process(pins.sync_process)
    with sim.write_vcd("tests/test_i2c_proto.vcd"):
        sim.run()


def test_i2c_reg_stream_8bit():
    dut = I2CRegStream(0x2C, 8, 8)
    sim = Simulator(dut)

    datas = {
        "addr": [0xAB, 0xCD],
        "val": [0xEF, 0x01],
    }

    out_stream = [
        0x2C << 1,
        0xAB,
        0xEF,

        0x2C << 1,
        0xCD,
        0x01,
    ]

    sender = StreamSimSender(dut.sink, datas, speed=0.9,
                             verbose=True, strname="sender")
    receiver = StreamSimReceiver(dut.source, length=len(out_stream), speed=1,
                                 verbose=True, strname="receiver")

    sim.add_clock(1e-6)
    sim.add_sync_process(sender.sync_process)
    sim.add_sync_process(receiver.sync_process)
    with sim.write_vcd("tests/test_i2c_reg_stream_8bit.vcd"):
        sim.run()

    assert receiver.data["data"] == out_stream


def test_i2c_reg_stream_16bit():
    dut = I2CRegStream(0x2C, 16, 16)
    sim = Simulator(dut)

    datas = {
        "addr": [0xABCD, 0xEF01],
        "val": [0x5A10, 0xA5BF],
    }

    out_stream = [
        0x2C << 1,
        0xAB,
        0xCD,
        0x5A,
        0x10,

        0x2C << 1,
        0xEF,
        0x01,
        0xA5,
        0xBF,
    ]

    sender = StreamSimSender(dut.sink, datas, speed=0.9,
                             verbose=True, strname="sender")
    receiver = StreamSimReceiver(dut.source, length=len(out_stream), speed=1,
                                 verbose=True, strname="receiver")

    sim.add_clock(1e-6)
    sim.add_sync_process(sender.sync_process)
    sim.add_sync_process(receiver.sync_process)
    with sim.write_vcd("tests/test_i2c_reg_stream_16bit.vcd"):
        sim.run()

    assert receiver.data["data"] == out_stream


if __name__ == "__main__":
    test_i2c_stream_writer()
    test_i2c_stream()
    test_i2c_proto()
    test_i2c_reg_stream_8bit()
    test_i2c_reg_stream_16bit()

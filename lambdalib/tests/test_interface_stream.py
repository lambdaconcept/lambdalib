# 2022 - LambdaConcept - po@lambdaconcept.com

from amaranth import *
from amaranth.sim import *

from lambdalib.interface import stream
from lambdalib.interface.stream_sim import *
from lambdalib.interface.stream_utils import *


def test_splitter():
    layout_from = [
        ("data",    8),
        ("other",   8),
        ("another", 8),
    ]
    layout_data = [
        ("data",    8),
    ]
    layout_other = [
        ("other",   8),
    ]
    layout_another = [
        ("another",   8),
    ]

    splitter = Splitter(layout_from,
                        layout_data, layout_other, layout_another)
    sim = Simulator(splitter)

    sinks = {
        "data":     [0x01, 0x02, 0x03, 0x04],
        "other":    [0xff, 0xfe, 0xfd, 0xfc],
        "another":  [0xa5, 0xa6, 0xa7, 0xa8],
    }
    length = len(sinks["data"])
    sender = StreamSimSender(splitter.sink, sinks, speed=0.8)

    receiver0 = StreamSimReceiver(splitter.sources[0],
                                 length=length,
                                 speed=0.8, verbose=True)
    receiver1 = StreamSimReceiver(splitter.sources[1],
                                 length=length,
                                 speed=0.6, verbose=True)
    receiver2 = StreamSimReceiver(splitter.sources[2],
                                 length=length,
                                 speed=0.2, verbose=True)

    sim.add_clock(1e-6)
    sim.add_sync_process(sender.sync_process)
    sim.add_sync_process(receiver0.sync_process)
    sim.add_sync_process(receiver1.sync_process)
    sim.add_sync_process(receiver2.sync_process)
    with sim.write_vcd("tests/test_stream_splitter.vcd"):
        sim.run()


def test_merger():
    layout_data = [
        ("data",    8),
    ]
    layout_other = [
        ("other",   8),
    ]
    layout_another = [
        ("another", 8),
    ]

    merger = Merger(layout_data, layout_other, layout_another)
    sim = Simulator(merger)

    sinks = [{
        "data":     [0x01, 0x02, 0x03, 0x04],
    }, {
        "other":    [0xff, 0xfe, 0xfd, 0xfc],
    }, {
        "another":  [0xa5, 0xa6, 0xa7, 0xa8],
    }]

    length = len(sinks[0]["data"])
    sender0 = StreamSimSender(merger.sinks[0], sinks[0], speed=0.5)
    sender1 = StreamSimSender(merger.sinks[1], sinks[1], speed=0.5)
    sender2 = StreamSimSender(merger.sinks[2], sinks[2], speed=0.5)

    receiver = StreamSimReceiver(merger.source,
                                 length=length,
                                 speed=0.8, verbose=True)

    sim.add_clock(1e-6)
    sim.add_sync_process(sender0.sync_process)
    sim.add_sync_process(sender1.sync_process)
    sim.add_sync_process(sender2.sync_process)
    sim.add_sync_process(receiver.sync_process)
    with sim.write_vcd("tests/test_stream_merger.vcd"):
        sim.run()


def test_last_inserter():
    inserter = LastInserter(3)(stream.Converter(8, 8))
    sim = Simulator(inserter)

    data = {
        "data": range(20),
        "last": [0]*19 + [1],
    }

    length = len(data["data"])
    sender = StreamSimSender(inserter.sink, data, speed=0.5)
    receiver = StreamSimReceiver(inserter.source,
                                 length=length,
                                 speed=0.8, verbose=True)

    sim.add_clock(1e-6)
    sim.add_sync_process(sender.sync_process)
    sim.add_sync_process(receiver.sync_process)
    with sim.write_vcd("tests/test_stream_last_inserter.vcd"):
        sim.run()


def test_last_timeout():
    lot = LastOnTimeout([("data", 8)], timeout=10)
    sim = Simulator(lot)

    data = {
        "data": range(20),
        "last": [0]*3 + [1] + [0]*10 + [1] + [0]*5,
    }

    length = len(data["data"])
    sender = StreamSimSender(lot.sink, data, speed=0.2)
    receiver = StreamSimReceiver(lot.source,
                                 length=length,
                                 speed=0.8, verbose=True)

    sim.add_clock(1e-6)
    sim.add_sync_process(sender.sync_process)
    sim.add_sync_process(receiver.sync_process)
    with sim.write_vcd("tests/test_stream_last_on_timeout.vcd"):
        sim.run()


if __name__ == "__main__":
    test_splitter(); print()
    test_merger(); print()
    test_last_inserter(); print()
    test_last_timeout(); print()

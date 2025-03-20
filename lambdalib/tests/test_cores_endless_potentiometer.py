from amaranth.sim import *
from lambdalib.interface.stream_sim import *
from lambdalib.cores.mech.endless_potentiometer import (
    EndlessPotentiometerDecoder,
    _ThresholdDetector,
    _DirectionDecoding,
)


def _wiper_to_adc(angular_position, phase_shift, adc_resolution):
    """Emulate sampled wiper output

    :param angular_position: Wiper absolute position in deg
    :param phase_shift: Phase shift in deg
    :param adc_resolution: ADC resolution in bits"""
    adc_max = (1 << adc_resolution) - 1

    angular_position += phase_shift

    # Make it 0-180-0
    periodic_angle = angular_position % 180
    if (angular_position // 180) & 1:
        periodic_angle = 180 - periodic_angle

    return int(adc_max * (periodic_angle / 180))



def test_wiper_to_adc():
    # W/o phase quadrature
    assert _wiper_to_adc(0, 0, 10) == 0
    assert _wiper_to_adc(90, 0, 10) == 1023//2
    assert _wiper_to_adc(180, 0, 10) == 1023
    assert _wiper_to_adc(270, 0, 10) == 1023//2
    assert _wiper_to_adc(360, 0, 10) == 0

    # W/ phase quadrature
    assert _wiper_to_adc(0, 90, 10) == 1023//2
    assert _wiper_to_adc(90, 90, 10) == 1023
    assert _wiper_to_adc(180, 90, 10) == 1023//2
    assert _wiper_to_adc(270, 90, 10) == 0
    assert _wiper_to_adc(360, 90, 10) == 1023//2


def test_threshold_detector():
    dut = _ThresholdDetector(width=8, threshold=16)
    sim = Simulator(dut)

    data = {
        "value": [
            0, 32, 0,
        ],
        "previous_value": [
            0, 0, 32,
        ]
    }

    tx = StreamSimSender(dut.readout, data, speed=0.3)
    rx = StreamSimReceiver(dut.detection, length=len(data["value"]), speed=0.8, verbose=True)

    sim.add_clock(1e-6)
    sim.add_sync_process(tx.sync_process)
    sim.add_sync_process(rx.sync_process)
    with sim.write_vcd("tests/test_threshold_detector.vcd"):
        sim.run()

    rx.verify({
        "up": [0, 1, 0],
        "down": [0, 0, 1],
        "value": [0, 32, 0],
        "delta": [0, 32, -32],
    })


def test_direction_decoding():
    dut = _DirectionDecoding(width=8)
    sim = Simulator(dut)

    ch_a = {
        "up": [
            1,
        ],
        "down": [
            0,
        ],
        "value": [
            0,
        ],
        "delta": [
            0,
        ],
    }
    ch_b = {
        "up": [
            1,
        ],
        "down": [
            0,
        ],
        "value": [
            0,
        ],
        "delta": [
            0,
        ],
    }

    tx_a = StreamSimSender(dut.dir_a, ch_a, speed=0.3)
    tx_b = StreamSimSender(dut.dir_b, ch_b, speed=0.3)
    rx = StreamSimReceiver(dut.direction, length=len(ch_a["value"]), speed=0.8, verbose=True)

    sim.add_clock(1e-6)
    sim.add_sync_process(tx_a.sync_process)
    sim.add_sync_process(tx_b.sync_process)
    sim.add_sync_process(rx.sync_process)
    with sim.write_vcd("tests/test_direction_decoding.vcd"):
        sim.run()


def test_endless_potentiometer_decoder_single():
    adc_resolution = 10  # bits

    dut = EndlessPotentiometerDecoder(adc_resolution, 5, 0.8)
    sim = Simulator(dut)

    ch_a = {
        "value": [_wiper_to_adc(90, 0, adc_resolution)],
        "previous_value": [_wiper_to_adc(0, 0, adc_resolution)],
    }
    ch_b = {
        "value": [_wiper_to_adc(90, 90, adc_resolution)],
        "previous_value": [_wiper_to_adc(90, 90, adc_resolution)],
    }

    tx_a = StreamSimSender(dut.ch_a, ch_a, speed=0.3)
    tx_b = StreamSimSender(dut.ch_b, ch_b, speed=0.3)
    rx = StreamSimReceiver(dut.position, 1, speed=0.8, verbose=True)

    sim.add_clock(1e-6)
    sim.add_sync_process(tx_a.sync_process)
    sim.add_sync_process(tx_b.sync_process)
    sim.add_sync_process(rx.sync_process)
    with sim.write_vcd("tests/test_endless_potentiometer_decoder_single.vcd"):
        sim.run()

    assert rx.data['diff'][0] == _wiper_to_adc(90, 0, adc_resolution)-_wiper_to_adc(0, 0, adc_resolution)


def test_endless_potentiometer_decoder():
    adc_resolution = 10  # bits

    dut = EndlessPotentiometerDecoder(adc_resolution, 2, 0.8)
    sim = Simulator(dut)

    wiper_a = [_wiper_to_adc(x, 0, adc_resolution) for x in range(720)]
    wiper_b = [_wiper_to_adc(x, 90, adc_resolution) for x in range(720)]

    ch_a = {
        "value": wiper_a[1:],
        "previous_value": wiper_a[:-1],
    }
    ch_b = {
        "value": wiper_b[1:],
        "previous_value": wiper_b[:-1],
    }

    tx_a = StreamSimSender(dut.ch_a, ch_a, speed=0.3)
    tx_b = StreamSimSender(dut.ch_b, ch_b, speed=0.3)
    rx = StreamSimReceiver(dut.position, length=len(ch_a["value"]), speed=0.8, verbose=True)

    sim.add_clock(1e-6)
    sim.add_sync_process(tx_a.sync_process)
    sim.add_sync_process(tx_b.sync_process)
    sim.add_sync_process(rx.sync_process)
    with sim.write_vcd("tests/test_endless_potentiometer_decoder.vcd"):
        sim.run()

    for x in rx.data['diff']:
        assert x in [5, 6]

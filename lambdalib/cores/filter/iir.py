# 2023 - LambdaConcept - po@lambdaconcept.com

import math
import scipy
import scipy.signal
from amaranth import *

from ...interface import stream
from ..math.multiplier import *


__all__ = ["IIRFilter"]


class IIRFilter(Elaboratable):
    def __init__(self, order, cutoff, samplerate, ripple=0.5,
                 filtertype="ellip", bandtype="lowpass", dynamic=False,
                 width=16, multiply_width=(25, 36)):
        self.order = order
        self.cutoff = cutoff
        self.samplerate = samplerate
        self.ripple = ripple
        self.width = width
        self.width_s = width_s = multiply_width[0]
        self.width_c = width_c = multiply_width[1]

        # Convert ripple from percent to dB
        rp = -20 * math.log10(1 - (ripple / 100))
        rs = -20 * math.log10(    (ripple / 100))

        # Generate filter coefficients
        if filtertype == "cheby1":
            self.b, self.a = scipy.signal.cheby1(order, rp, cutoff,
                                                 btype=bandtype, fs=samplerate)
        elif filtertype == "ellip":
            self.b, self.a = scipy.signal.ellip(order, rp, rs, cutoff,
                                                btype=bandtype, fs=samplerate)
        else:
            raise NotImplementedError
        print("b:", self.b)
        print("a:", self.a)

        # Find the best fixed point shift
        coeffs = [*self.b, *self.a]
        cmax   = max(map(abs, coeffs))
        nbits  = math.ceil(math.log2(cmax + 1))
        self.shift_c = width_c - nbits -1 # -1 for sign bit
        print(f"coeff max: {cmax}")
        print(f"coeff shift: {nbits}.{self.shift_c}")

        self.b_fp = [int(v * (2**self.shift_c)) for v in self.b]
        self.a_fp = [int(v * (2**self.shift_c)) for v in self.a]
        print("b_fp:", self.b_fp)
        print("a_fp:", self.a_fp)

        # Dynamic mode:
        #  filter coefficients can be updated on the fly
        #  to change the filter caracteristics.
        if dynamic:
            self.b_regs = Array([Signal(signed(width_c), reset= v, name=f"b_reg_{i}")
                                for i, v in enumerate(self.b_fp)])
            self.a_regs = Array([Signal(signed(width_c), reset=-v, name=f"a_reg_{i}")
                                for i, v in enumerate(self.a_fp)])
        else:
            self.b_regs = Array([Const( v, signed(width_c)) for v in self.b_fp])
            self.a_regs = Array([Const(-v, signed(width_c)) for v in self.a_fp])

        # Input / Output streams
        self.sink   = stream.Endpoint([("data", signed(width))])
        self.source = stream.Endpoint([("data", signed(width))])

        # Increase precision on internally stored output signals
        self.shift_s = width_s - width
        assert(self.shift_s >= 0)
        print(f"signal shift: {self.shift_s}")


    def elaborate(self, platform):
        sink = self.sink
        source = self.source
        width_s = self.width_s
        shift_s = self.shift_s
        width_c = self.width_c
        shift_c = self.shift_c

        m = Module()

        size   = len(self.a_regs)
        idx    = Signal(range(size))
        i_regs = Array([Signal(signed(width_s), name=f"i_reg_{i}")
                       for i in range(size)])
        o_regs = Array([Signal(signed(width_s), name=f"o_reg_{i}")
                       for i in range(size)])

        m.submodules.mult = \
                     mult = Multiplier(signed(width_s), signed(width_c))
        c_r         = Signal.like(mult.o.c)
        valid_r     = Signal()
        last_r      = Signal()
        sum_r       = Signal.like(mult.o.c)


        with m.FSM() as fsm:

            with m.State("IDLE"):
                m.d.sync += sum_r.eq(0)

                m.d.comb += sink.ready.eq(1)
                with m.If(sink.valid):

                    m.d.sync += i_regs[0].eq(sink.data << shift_s)
                    for i in range(size - 1):
                        m.d.sync += i_regs[i+1].eq(i_regs[i])

                    m.d.sync += o_regs[0].eq(0)
                    for i in range(size - 1):
                        m.d.sync += o_regs[i+1].eq(o_regs[i])

                    m.next = "RUN_B"

            with m.State("RUN_B"):
                # Queue B x I mults
                m.d.comb += [
                    mult.i.a    .eq(     i_regs[idx]),
                    mult.i.b    .eq(self.b_regs[idx]),
                    mult.i.valid.eq(1),
                ]
                with m.If(mult.i.ready):
                    with m.If(idx < (size-1)):
                        m.d.sync += idx.eq(idx + 1)
                    with m.Else():
                        m.d.sync += idx.eq(1)
                        m.next = "RUN_A"

            with m.State("RUN_A"):
                # Queue A x O mults
                m.d.comb += [
                    mult.i.a    .eq(     o_regs[idx]),
                    mult.i.b    .eq(self.a_regs[idx]),
                    mult.i.valid.eq(1),
                    mult.i.last .eq(idx == (size-1)),
                ]
                with m.If(mult.i.ready):
                    with m.If(idx < (size-1)):
                        m.d.sync += idx.eq(idx + 1)
                    with m.Else():
                        m.d.sync += idx.eq(0)
                        m.next = "WAIT"

            with m.State("WAIT"):
                # Wait for the last multiply result
                with m.If(valid_r & last_r):
                    m.next = "OUTPUT"

            with m.State("OUTPUT"):
                # Send the sum result to the output stream
                m.d.sync += o_regs[0].eq(sum_r >> shift_c)
                m.d.comb += [
                    source.valid.eq(1),
                    source.data .eq(sum_r >> (shift_c + shift_s)),
                ]
                with m.If(source.ready):
                    m.next = "IDLE"


        # Store multiply results
        m.d.comb += mult.o.ready.eq(1)
        m.d.sync += [
            c_r    .eq(mult.o.c),
            valid_r.eq(mult.o.valid),
            last_r .eq(mult.o.last),
        ]

        # Compute the sum
        with m.If(valid_r):
            m.d.sync += sum_r.eq(sum_r + c_r)

        return m

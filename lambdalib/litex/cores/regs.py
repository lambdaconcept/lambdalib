# 2023 - LambdaConcept - po@lambdaconcept.com

from migen import *
from litex.gen.common import reverse_bytes
from litex.soc.interconnect.csr import *
from litex.soc.interconnect.csr_eventmanager import *
from litex.soc.interconnect import stream


__all__ = [
    "StreamRegs",
    "RegsStream",
]


class StreamRegs(Module, AutoCSR):
    def __init__(self, depth, width=32, reverse=False):
        self.sink = sink = stream.Endpoint([("data", width)])

        # Data regs
        self._regs = []
        for i in range(depth):
            name = "reg_{}".format(i)
            csr = CSRStatus(width, name=name)
            setattr(self, name, csr)
            self._regs.append(csr)
        regs = Array(self._regs)

        # Interrupt
        self.submodules.ev = EventManager()
        self.ev.drdy = EventSourcePulse(description="Indicates the register values have been all updated.")
        self.ev.finalize()

        # # #

        idx = Signal(max=depth)

        self.comb += sink.ready.eq(1)
        self.sync += [
            If(sink.valid,
                # Update register values
                regs[idx].status.eq(sink.data if not reverse else reverse_bytes(sink.data)),

                # Increment register address
                If((idx == depth - 1) | sink.last,
                    idx.eq(0),
                ).Else(
                    idx.eq(idx + 1),
                ),
            ),
        ]

        # Trigger interrupt
        self.comb += [
            If(sink.valid & sink.ready & sink.last,
                self.ev.drdy.trigger.eq(1),
            ),
        ]


class RegsStream(Module, AutoCSR):
    def __init__(self, width=32, fifo_depth=8):
        self.submodules.fifo = fifo = stream.SyncFIFO([("data", width)], fifo_depth, buffered=True)
        self.source = fifo.source

        self.data = data = CSRStorage(width)
        self.last = last = CSRStorage()

        # # #

        self.comb += [
            fifo.sink.data.eq(data.storage),
            fifo.sink.valid.eq(data.re),
            fifo.sink.last.eq(last.storage),
        ]

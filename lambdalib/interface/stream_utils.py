# 2022 - LambdaConcept - po@lambdaconcept.com

from amaranth import *

from . import stream


__all__ = [
    "Stitcher",
    "Splitter",
    "Merger",
]


class Stitcher(Elaboratable):
    """ Stream stitcher module.

    This module remove the first/last from the sink stream every `count` times.
    Successive packets from the incoming stream are grouped 'stitched' together.
    """
    def __init__(self, layout, count):
        self.count = count
        self.sink = stream.Endpoint(layout)
        self.source = stream.Endpoint(layout)

    def elaborate(self, platform):
        sink = self.sink
        source = self.source
        count = self.count

        m = Module()

        f_idx = Signal(range(count))
        l_idx = Signal(range(count))

        m.d.comb += [
            sink.connect(source, exclude={"first", "last"}),

            source.first.eq(sink.first & (f_idx == 0)),
            source.last .eq(sink.last  & (l_idx == count - 1)),
        ]

        with m.If(sink.valid & sink.ready & sink.first):
            with m.If(f_idx < count - 1):
                m.d.sync += f_idx.eq(f_idx + 1)
            with m.Else():
                m.d.sync += f_idx.eq(0)

        with m.If(sink.valid & sink.ready & sink.last):
            with m.If(l_idx < count - 1):
                m.d.sync += l_idx.eq(l_idx + 1)
            with m.Else():
                m.d.sync += l_idx.eq(0)

        return m


class Splitter(Elaboratable):
    """ Stream splitter module.

    This module splits the different fields from one sink stream into several
    source streams according to the layout passed as parameters.
    """
    def __init__(self, layout_from, *layouts_to):
        self.layouts_to = layouts_to
        self.n = len(layouts_to)

        self.sink = stream.Endpoint(layout_from)
        self.sources = []
        for i, layout in enumerate(layouts_to):
            self.sources.append(stream.Endpoint(layout))

        used = set()
        fields = set([f[0] for f in layout_from])
        for layout in layouts_to:
            for f in layout:
                if not f[0] in fields:
                    raise ValueError(f[0] + " not found in layout from")
                if f[0] in used:
                    raise ValueError(f[0] + " already used in layout to")
                used.add(f[0])

    def elaborate(self, platform):
        sink = self.sink
        sources = self.sources

        m = Module()

        done = Signal(self.n)

        # Each individual stream is valid when we have something
        # to forward from the sink, and stops being valid when
        # the data has been transfered but we are still waiting
        # for other source streams to forward their own data.
        for i in range(self.n):
            m.d.comb += sources[i].valid.eq(sink.valid & ~done[i])

        # We acknowledge the data from the sink when all source streams
        # are done tranferring their data.
        aggregate = [sources[i].ready | done[i]
                     for i in range(self.n)]
        ready = Cat(*aggregate).all()
        m.d.comb += sink.ready.eq(ready)

        flow = [sources[i].valid & sources[i].ready
                for i in range(self.n)]
        aggregate = [flow[i] | done[i]
                     for i in range(self.n)]
        end = Cat(*aggregate).all()

        # Reset all the done signals when the data has been fully
        # transfered on all source streams.
        with m.If(end):
            m.d.sync += done.eq(0)

        # Only some of the source streams are ready, individualy
        # mark them as done.
        with m.Else():
            for i in range(self.n):
                with m.If(flow[i]):
                    m.d.sync += done[i].eq(1)

        for src in sources:
            m.d.comb += [
                src.first.eq(sink.first),
                src.last.eq(sink.last),
            ]

        # Actually split the payloads
        for i, layout in enumerate(self.layouts_to):
            for f in layout:
                m.d.comb += getattr(sources[i], f[0]).eq(getattr(sink, f[0]))

        return m


class Merger(Elaboratable):
    """ Stream merger module.

    This module merges all the fields coming from multiple sink streams
    into one unique source stream containing all the fields.
    """
    def __init__(self, *layouts_from):
        self.layouts_from = layouts_from
        self.n = len(layouts_from)

        layout_to = []
        fields = set()
        self.sinks = []
        for i, layout in enumerate(layouts_from):
            for f in layout:
                if f[0] in fields:
                    raise ValueError(f[0] + " duplicate field in layout")
                fields.add(f[0])
            layout_to += layout
            self.sinks.append(stream.Endpoint(layout))

        self.buffer = stream.PipeValid(layout_to)
        self.source = self.buffer.source

    def elaborate(self, platform):
        sinks = self.sinks
        source = self.buffer.sink

        m = Module()
        m.submodules.buffer = self.buffer

        # We wait for all input streams to be valid before
        # forwarding the data.
        aggregate = [sinks[i].valid for i in range(self.n)]
        valid = Cat(*aggregate).all()
        m.d.comb += source.valid.eq(valid)

        # We acknowledge the data from all the input streams
        # together at the same cycle when it is consumed on the source.
        for i in range(self.n):
            m.d.comb += sinks[i].ready.eq(source.valid & source.ready)

        # Merge strategy concerning first and last signals:
        # we 'or' the signals from the sinks streams.
        aggregate = [sinks[i].first for i in range(self.n)]
        first = Cat(*aggregate).any()
        aggregate = [sinks[i].last for i in range(self.n)]
        last = Cat(*aggregate).any()

        m.d.comb += [
            source.first.eq(first),
            source.last.eq(last),
        ]

        # Actually merge the payloads
        for i, layout in enumerate(self.layouts_from):
            for f in layout:
                m.d.comb += getattr(source, f[0]).eq(getattr(sinks[i], f[0]))

        return m

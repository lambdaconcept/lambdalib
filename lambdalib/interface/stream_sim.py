# 2022 - LambdaConcept - po@lambdaconcept.com

import random
from collections import defaultdict

from amaranth import *
from amaranth.sim import *


__all__ = [
    "StreamSimSender",
    "StreamSimReceiver",
    "StreamSimConnect",
]


class StreamSimSender:
    def __init__(self, sink, data, speed=0.5, initial_delay=0,
            verbose=False, decimal=False, strname=""):
        self.sink = sink
        self.data = data
        self.speed = speed
        self.initial_delay = initial_delay
        self.verbose = verbose
        self.decimal = decimal
        self.strname = strname

        if isinstance(self.data, list):
            self.data = {"data": self.data}

        self.length = 0
        for v in self.data.values():
            self.length = len(v)
            break

    def sync_process(self):
        sink = self.sink

        for i in range(self.initial_delay):
            yield

        i = 0
        while i < self.length:
            for k, v in self.data.items():
                yield getattr(sink, k).eq(v[i])

            if (not (yield sink.valid) \
                    or ((yield sink.valid) and (yield sink.ready))) \
                    and (random.random() < self.speed):
                yield sink.valid.eq(1)

            yield

            if (yield sink.valid) and (yield sink.ready):
                if self.verbose:
                    for k, v in self.data.items():
                        print(self.strname, "\t", k, hex(v[i]) if not self.decimal else v[i])

                i += 1
                yield sink.valid.eq(0)


class StreamSimReceiver:
    def __init__(self, source, length=None, speed=0.5, initial_delay=0,
            verbose=False, callback=None, decimal=False, strname=""):
        self.source = source
        self.data = defaultdict(list)
        self.length = length
        self.speed = speed
        self.initial_delay = initial_delay
        self.verbose = verbose
        self.callback = callback
        self.decimal = decimal
        self.strname = strname

    def sync_process(self):
        source = self.source
        fields = source.fields["payload"].fields.items()

        if self.length is None:
            yield Passive()

        for i in range(self.initial_delay):
            yield

        i = 0
        while not i == self.length:
            if ((yield source.valid) and (random.random() < self.speed)) \
                    or self.speed == 1.0:
                yield source.ready.eq(1)
            else:
                yield source.ready.eq(0)

            yield

            if (yield source.valid) and (yield source.ready):
                i += 1
                current = {}

                for name, sig in fields:
                    val = (yield sig)
                    current[name] = val
                    self.data[name].append(val)
                    if self.verbose:
                        print(self.strname, "\t", name, hex(val) if not self.decimal else val)

                for name in ["first", "last"]:
                    val = (yield getattr(source, name))
                    current[name] = val
                    self.data[name].append(val)
                    if self.verbose:
                        if val:
                            print(self.strname, "\t", "[{}]".format(name))

                if self.callback:
                    self.callback(current)

    def verify(self, expected):
        print("\nVerify:")

        for k in expected.keys():
            e = expected[k]
            v = self.data[k]
            if len(e) != len(v):
                raise AssertionError("Failed length differs for key '{}': has: {}, expected: {}".format(k, len(v), len(e)))

        for k in expected.keys():
            v = expected[k]
            print("checking {}, len {}".format(k, len(v)))
            for i in range(len(v)):
                r = self.data[k][i]
                e = expected[k][i]
                try:
                    assert(r == e)
                except AssertionError as err:
                    print("Failed @{}: received: {:02x}, expected: {:02x}".format(i, r, e))
                    raise err

        print("OK\n")


class StreamSimConnect:
    def __init__(self, source, sink, omit=None, remap=None, speed=0.5):
        self.source = source
        self.sink = sink
        self.speed = speed
        self.omit = omit if omit else {}
        self.remap = remap if remap else {}

    def sync_process(self):
        source = self.source
        sink = self.sink
        fields = source.fields["payload"].fields.items()

        yield Passive()

        store = defaultdict(int)
        stored = False

        while True:

            yield source.ready.eq(0)
            yield

            if not stored \
                    and (yield source.valid) \
                    and (random.random() < self.speed):

                for name, sig in fields:
                    store[name] = (yield sig)
                for name in ["first", "last"]:
                    store[name] = (yield getattr(source, name))

                stored = True

                yield source.ready.eq(1)
                yield

            elif stored and (random.random() < self.speed):

                for name, sig in fields:
                    new = name
                    if name in self.remap:
                        new = self.remap[name]
                    if not new in self.omit:
                        yield getattr(sink, new).eq(store[name])
                for name in ["first", "last"]:
                    yield getattr(sink, name).eq(store[name])

                yield sink.valid.eq(1)
                yield

                while not (yield sink.ready):
                    yield

                yield sink.valid.eq(0)
                yield
                stored = False

# 2022 - LambdaConcept - po@lambdaconcept.com

from amaranth import *

from luna.usb2 import *

from lambdalib.interface import stream


__all__ = [
    "USBAsyncStreamOutEndpoint",
    "USBAsyncStreamInEndpoint",
    "usb_ep_description",
]


usb_ep_description = [
    ("data", 8),
]


class USBAsyncStreamOutEndpoint(USBStreamOutEndpoint):
    def __init__(self, w_domain="usb", r_domain="sync", **kwargs):
        super().__init__(**kwargs)

        # Endpoints are in domain "usb", use clock domain crossing
        self.cdc_out = stream.AsyncFIFO(usb_ep_description, 8,
            w_domain=w_domain, r_domain=r_domain,
            buffered=True,
        )
        self.source = self.cdc_out.source

    def elaborate(self, platform):
        cdc_out = self.cdc_out

        m = super().elaborate(platform)

        m.submodules.cdc_out = cdc_out

        m.d.comb += [
            cdc_out.sink.data.eq(self.stream.payload),
            cdc_out.sink.valid.eq(self.stream.valid),
            cdc_out.sink.last.eq(self.stream.last),
            self.stream.ready.eq(cdc_out.sink.ready),
        ]

        return m


class USBAsyncStreamInEndpoint(USBStreamInEndpoint):
    def __init__(self, w_domain="sync", r_domain="usb", **kwargs):
        super().__init__(**kwargs)

        # Endpoints are in domain "usb", use clock domain crossing
        self.cdc_in = stream.AsyncFIFO(usb_ep_description, 8,
            w_domain=w_domain, r_domain=r_domain,
            buffered=True,
        )
        self.sink = self.cdc_in.sink

    def elaborate(self, platform):
        cdc_in = self.cdc_in

        m = super().elaborate(platform)

        m.submodules.cdc_in = cdc_in

        m.d.comb += [
            self.stream.payload.eq(cdc_in.source.data),
            self.stream.valid.eq(cdc_in.source.valid),
            self.stream.last.eq(cdc_in.source.last),
            cdc_in.source.ready.eq(self.stream.ready),
        ]

        return m

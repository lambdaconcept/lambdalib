# 2022 - LambdaConcept - po@lambdaconcept.com

from amaranth import *

from usb_protocol.emitters import DeviceDescriptorCollection
from luna.usb2 import USBDevice, USBStreamOutEndpoint, USBStreamInEndpoint

from .endpoint_cdc import *
from lambdalib.interface import stream


__all__ = ["USBGenericDevice"]


class USBGenericDevice(Elaboratable):
    """ Simple device with an arbitrary number of pairs of endpoints (IN + OUT).
    """

    BULK_ENDPOINT_NUMBER = 1
    BULK_PACKET_SIZE_HS  = 512
    BULK_PACKET_SIZE_FS  = 64

    def __init__(self, pins,
            pid=0x1234, vid=0xffff,
            i_manufacturer="LUNA",
            i_product="Generic Bulk",
            i_serial="",
            ep_pairs=1,
            **kwargs):

        self.pins = pins

        self.pid = pid
        self.vid = vid
        self.i_manufacturer = i_manufacturer
        self.i_product      = i_product
        self.i_serial       = i_serial

        self.ep_pairs = ep_pairs

        self.kwargs = kwargs

        self.sinks   = [stream.Endpoint(usb_ep_description, name="sink_" + str(i))
                            for i in range(ep_pairs)]
        self.sources = [stream.Endpoint(usb_ep_description, name="source_" + str(i))
                            for i in range(ep_pairs)]
        # For convenience
        if ep_pairs == 1:
            self.sink   = self.sinks[0]
            self.source = self.sources[0]
        else:
            for i in range(self.ep_pairs):
                setattr(self, "sink_"   + str(i), self.sinks[i])
                setattr(self, "source_" + str(i), self.sources[i])

        self.max_packet_size = self.BULK_PACKET_SIZE_HS if hasattr(pins, "dir") \
                          else self.BULK_PACKET_SIZE_FS

        self.tx_activity = Signal(self.ep_pairs)
        self.rx_activity = Signal(self.ep_pairs)

    def create_descriptors(self):
        """ Create the descriptors we want to use for our device. """

        descriptors = DeviceDescriptorCollection()

        with descriptors.DeviceDescriptor() as d:
            d.idVendor           = self.vid
            d.idProduct          = self.pid

            d.iManufacturer      = self.i_manufacturer
            d.iProduct           = self.i_product
            d.iSerialNumber      = self.i_serial

            d.bNumConfigurations = 1

        with descriptors.ConfigurationDescriptor() as c:

            with c.InterfaceDescriptor() as i:
                i.bInterfaceNumber = 0

                for k in range(self.ep_pairs):
                    with i.EndpointDescriptor() as e:
                        e.bEndpointAddress = self.BULK_ENDPOINT_NUMBER + k
                        e.wMaxPacketSize   = self.max_packet_size

                    with i.EndpointDescriptor() as e:
                        e.bEndpointAddress = 0x80 | (self.BULK_ENDPOINT_NUMBER + k)
                        e.wMaxPacketSize   = self.max_packet_size

        return descriptors

    def elaborate(self, platform):
        m = Module()

        m.submodules.usb = usb = USBDevice(bus=self.pins, **self.kwargs)

        # Add our standard control endpoint to the device.
        descriptors = self.create_descriptors()
        usb.add_standard_control_endpoint(descriptors)

        for k in range(self.ep_pairs):
            # Add a stream endpoint to our device.
            stream_out_ep = USBAsyncStreamOutEndpoint(
                endpoint_number=self.BULK_ENDPOINT_NUMBER + k,
                max_packet_size=self.max_packet_size,
            )
            usb.add_endpoint(stream_out_ep)
            m.d.comb += stream_out_ep.source.connect(self.sources[k])

            # Add a stream endpoint to our device.
            stream_in_ep = USBAsyncStreamInEndpoint(
                endpoint_number=self.BULK_ENDPOINT_NUMBER + k,
                max_packet_size=self.max_packet_size,
            )
            usb.add_endpoint(stream_in_ep)
            m.d.comb += self.sinks[k].connect(stream_in_ep.sink)

        m.d.comb += usb.connect.eq(1)

        # Activity & Status
        for k in range(self.ep_pairs):
            m.d.comb += [
                self.tx_activity[k].eq(self.sinks  [k].valid & self.sinks  [k].ready),
                self.rx_activity[k].eq(self.sources[k].valid & self.sources[k].ready),
            ]

        return m

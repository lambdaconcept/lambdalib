# 2022 - LambdaConcept - po@lambdaconcept.com

from amaranth import *

from usb_protocol.emitters import DeviceDescriptorCollection
from usb_protocol.emitters.descriptors.standard import get_string_descriptor
from usb_protocol.emitters.descriptors.microsoft10 import MicrosoftOS10DescriptorCollection
from usb_protocol.types.descriptors.microsoft10 import RegistryTypes
from luna.usb2 import USBDevice, USBStreamOutEndpoint, USBStreamInEndpoint
from luna.gateware.usb.request.windows import MicrosoftOS10RequestHandler

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
            ep_sizes=None,
            max_packet_size=None,
            with_cdc=True,
            with_microsoft_os_1_0=False,        # Set to True for interface 0,
                                                # or pass a list() of interfaces
            bufferize_ep_in=True,
            custom_ep=[],
            **kwargs):

        self.pins = pins

        self.pid = pid
        self.vid = vid
        self.i_manufacturer = i_manufacturer
        self.i_product      = i_product
        self.i_serial       = i_serial

        if max_packet_size is None:
            self.max_packet_size = self.BULK_PACKET_SIZE_FS if hasattr(pins, "d_n") \
                              else self.BULK_PACKET_SIZE_HS
        else:
            self.max_packet_size = max_packet_size

        if ep_sizes is None:
            ep_sizes = [(self.max_packet_size, self.max_packet_size)
                            for k in range(ep_pairs)]
        else:
            ep_pairs = len(ep_sizes)

        self.ep_pairs = ep_pairs
        self.ep_sizes = ep_sizes
        self.control_ep_handlers = []
        self.with_cdc = with_cdc
        self.with_microsoft_os_1_0 = with_microsoft_os_1_0
        self.bufferize_ep_in = bufferize_ep_in

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

        self.tx_activity = Signal(self.ep_pairs)
        self.rx_activity = Signal(self.ep_pairs)
        self.custom_ep = custom_ep

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

                for k, (imax, omax) in enumerate(self.ep_sizes):
                    if omax != 0:
                        with i.EndpointDescriptor() as e:
                            e.bEndpointAddress = self.BULK_ENDPOINT_NUMBER + k
                            e.wMaxPacketSize   = omax

                    if imax != 0:
                        with i.EndpointDescriptor() as e:
                            e.bEndpointAddress = 0x80 | (self.BULK_ENDPOINT_NUMBER + k)
                            e.wMaxPacketSize   = imax

        return descriptors

    def add_microsoft_os_1_0(self, descriptors):
        """ Add Microsoft OS 1.0 descriptors for Windows compatibility. """
        descriptors.add_descriptor(get_string_descriptor("MSFT100\xee"), index=0xee)

        msft_descriptors = MicrosoftOS10DescriptorCollection()

        # When not passed explicitely as an interface list, consider
        # just the first interface number 0 as Windows compatible.
        if isinstance(self.with_microsoft_os_1_0, bool):
            self.with_microsoft_os_1_0 = [0]

        with msft_descriptors.ExtendedCompatIDDescriptor() as c:
            # Declare all interfaces from the list as Windows compatible
            for intf in self.with_microsoft_os_1_0:
                with c.Function() as f:
                    f.bFirstInterfaceNumber = intf
                    f.compatibleID          = "WINUSB"

        with msft_descriptors.ExtendedPropertiesDescriptor() as d:
            with d.Property() as p:
                # Windows defined ClassGUID for "USBDevice"
                p.dwPropertyDataType = RegistryTypes.REG_SZ
                p.PropertyName       = "DeviceInterfaceGUID"
                p.PropertyData       = "{88bae032-5a81-49f0-bc3d-a4ff138216d6}"

        msft_handler = MicrosoftOS10RequestHandler(msft_descriptors, request_code=0xee)
        self.add_control_ep_handler(msft_handler)

    def add_control_ep_handler(self, handler):
        self.control_ep_handlers.append(handler)

    def elaborate(self, platform):
        m = Module()

        m.submodules.usb = usb = USBDevice(bus=self.pins, **self.kwargs)

        # Add our standard control endpoint to the device.
        descriptors = self.create_descriptors()

        # Optionally add handlers for Microsoft descriptors.
        if self.with_microsoft_os_1_0:
            self.add_microsoft_os_1_0(descriptors)

        control_ep = usb.add_standard_control_endpoint(
            descriptors,
            # Windows compatible descriptors cannot be build in block ram
            # because MSFT string at index 0xee is not contiguous.
            avoid_blockram=False,
        )

        # Add optional custom requests handlers (vendor)
        for handler in self.control_ep_handlers:
            control_ep.add_request_handler(handler)

        # Instanciate or not cross domain endpoints
        if self.with_cdc:
            ep_o_cls = USBAsyncStreamOutEndpoint
            ep_i_cls = USBAsyncStreamInEndpoint
        else:
            ep_o_cls = USBSyncStreamOutEndpoint
            ep_i_cls = USBSyncStreamInEndpoint

        for k, (i, o) in enumerate(self.ep_sizes):
            # Add a stream OUT endpoint to our device.
            if o != 0:
                stream_out_ep = ep_o_cls(
                    endpoint_number=self.BULK_ENDPOINT_NUMBER + k,
                    max_packet_size=o,
                )
                usb.add_endpoint(stream_out_ep)
                m.d.comb += stream_out_ep.source.connect(self.sources[k])

            # Add a stream IN endpoint to our device.
            if i != 0:
                stream_in_ep = ep_i_cls(
                    endpoint_number=self.BULK_ENDPOINT_NUMBER + k,
                    max_packet_size=i,
                    bufferize_output=self.bufferize_ep_in,
                )
                usb.add_endpoint(stream_in_ep)
                m.d.comb += self.sinks[k].connect(stream_in_ep.sink)

        for ep in self.custom_ep:
            usb.add_endpoint(ep)

        m.d.comb += usb.connect.eq(1)

        # Activity & Status
        for k in range(self.ep_pairs):
            m.d.comb += [
                self.tx_activity[k].eq(self.sinks  [k].valid & self.sinks  [k].ready),
                self.rx_activity[k].eq(self.sources[k].valid & self.sources[k].ready),
            ]

        return m

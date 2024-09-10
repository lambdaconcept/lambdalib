# 2022 - LambdaConcept - po@lambdaconcept.com

import usb1


__all__ = ["USBDevice"]


class USBEndpoint():
    def __init__(self, handle, size, num, asynchronous=True, context=None, timeout=1000):
        self.handle = handle
        self.size = size
        self.num = num
        self.asynchronous = asynchronous
        self.context = context
        self.timeout = timeout

        # function alias
        self.write = self.send
        self.read = self.recv

    def cb_wr(self, xfr):
        # print("cb wr", xfr.getStatus())
        self.wbusy = False

    def cb_rd(self, xfr):
        # print("cb rd", xfr.getStatus())
        length = xfr.getActualLength()
        self.rdata = xfr.getBuffer()[0:length]
        self.rbusy = False

    def send(self, data):
        if not self.asynchronous:
            return self.handle.bulkWrite(self.num, bytearray(data),
                                         timeout=self.timeout)

        else:
            self.wbusy = True
            xfr = self.handle.getTransfer()
            xfr.setBulk(self.num | usb1.ENDPOINT_OUT, bytearray(data),
                        callback=self.cb_wr)
            xfr.submit()

    def recv(self, length=None):
        if length is None:
            length = self.size

        if not self.asynchronous:
            try:
                return self.handle.bulkRead(self.num, length, timeout=self.timeout)
            except usb1.USBErrorTimeout:
                return []

        else:
            self.rbusy = True
            xfr = self.handle.getTransfer()
            xfr.setBulk(self.num | usb1.ENDPOINT_IN, length, callback=self.cb_rd)
            xfr.submit()

            while self.rbusy:
                self.context.handleEvents()
            return self.rdata

    def exchange(self, data):
        self.send(data)
        return self.recv(len(data))


class USBDevice():
    def __init__(self, bulksize, pid=0x1234, vid=0xffff, idx=0, interface=0):
        self.bulksize = bulksize
        self.pid = pid
        self.vid = vid
        self.interface = interface

        self.handle = None
        self.context = usb1.USBContext()

        index = 0
        for device in self.context.getDeviceList(skip_on_error=True):
            if device.getVendorID()  == vid and \
               device.getProductID() == pid:

                if index == idx:
                    self.handle = device.open()
                    break
                index += 1

        if self.handle is None:
            raise usb1.USBError("Device not present, check udev rules")
        self.handle.claimInterface(self.interface)

    def get_endpoint(self, num, asynchronous=True):
        return USBEndpoint(self.handle, self.bulksize, num,
                           asynchronous=asynchronous, context=self.context)

    def __del__(self):
        if self.handle:
            self.handle.releaseInterface(self.interface)
        self.context.close()

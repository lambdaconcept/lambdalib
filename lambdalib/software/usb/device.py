# 2022 - LambdaConcept - po@lambdaconcept.com

import usb1


__all__ = ["USBDevice"]


class USBEndpoint():
    def __init__(self, handle, size, num):
        self.handle = handle
        self.size = size
        self.num = num

        # function alias
        self.write = self.send
        self.read = self.recv

    def send(self, data):
        self.handle.bulkWrite(self.num, bytearray(data), timeout=1000)

    def recv(self, length=None):
        if length is None:
            length = self.size
        try:
            return self.handle.bulkRead(self.num, length, timeout=1000)
        except usb1.USBErrorTimeout:
            return []

    def exchange(self, data):
        self.send(data)
        return self.recv(len(data))


class USBDevice():
    INTERFACE   = 0

    def __init__(self, bulksize, pid=0x1234, vid=0xffff):
        self.bulksize = bulksize
        self.pid = pid
        self.vid = vid

        self.context = usb1.USBContext()
        self.handle = self.context.openByVendorIDAndProductID(
            self.vid,
            self.pid,
            skip_on_error=True,
        )
        if self.handle is None:
            raise usb1.USBError("Device not present, check udev rules")
        self.handle.claimInterface(self.INTERFACE)

    def get_endpoint(self, num):
        return USBEndpoint(self.handle, self.bulksize, num)

    def __del__(self):
        if self.handle:
            self.handle.releaseInterface(self.INTERFACE)
        self.context.close()

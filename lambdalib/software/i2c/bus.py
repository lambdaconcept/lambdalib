# 2023 - LambdaConcept - po@lambdaconcept.com

import sys


__all__ = ["I2CBus"]


I2C_WRITE   = 0
I2C_READ    = 1

STATUS_OK   = 0
STATUS_ERR  = 1


class I2CBus:
    def __init__(self, dev, reg_addr_width=8):
        self.dev = dev
        self.reg_addr_width = reg_addr_width

    def write_byte_data(self, addr, reg, data):
        self.write_block_data(addr, reg, [data])

    def read_byte_data(self, addr, reg):
        return self.read_block_data(addr, reg, 1)[0]

    def write_block_data(self, addr, reg, data):
        reg_addr_size = self.reg_addr_width // 8
        reg_addr_array = []
        for _ in range(reg_addr_size):
            reg_addr_array.append(reg & 0xff)
            reg = reg >> 8
        reg_addr_array.reverse()

        size = reg_addr_size + len(data)
        array = reg_addr_array + data

        # write register address and data
        buffer = bytearray([(addr << 1) | I2C_WRITE, size, *array])
        self.dev.write(buffer)

        status = self.dev.read(1)[0]
        if status != STATUS_OK:
            return None

        return len(data)

    def read_block_data(self, addr, reg, length):
        reg_addr_size = self.reg_addr_width // 8
        reg_addr_array = []
        for _ in range(reg_addr_size):
            reg_addr_array.append(reg & 0xff)
            reg = reg >> 8
        reg_addr_array.reverse()

        # write register address
        buffer = bytearray([(addr << 1) | I2C_WRITE, reg_addr_size, *reg_addr_array])
        self.dev.write(buffer)

        status = self.dev.read(1)[0]
        if status != STATUS_OK:
            return None

        # read block
        buffer = bytearray([(addr << 1) | I2C_READ, length])
        self.dev.write(buffer)

        status = self.dev.read(1)[0]
        if status != STATUS_OK:
            return None

        block = self.dev.read(length)
        return block

    def discover(self):
        print("Discovering...")

        for addr in range(0, 128): # 7 bits addr

            length = 0
            buffer = bytearray([(addr << 1) | I2C_WRITE, length])

            self.dev.write(buffer)

            status = self.dev.read(1)[0]
            if status != STATUS_OK:
                sys.stdout.write(".. ")
                sys.stdout.flush()
            else:
                sys.stdout.write(f"{addr:02x} ")
                sys.stdout.flush()

            if (addr % 16) == 15:
                sys.stdout.write("\n")
                sys.stdout.flush()

    def discover_queue(self):
        print("Discovering...")

        buffer = bytearray()
        for addr in range(0, 128): # 7 bits addr

            length = 0
            buffer += bytearray([(addr << 1) | I2C_WRITE, length])

        # Queing all requests requires a good FIFO on board!
        self.dev.write(buffer)

        status = self.dev.read(128)
        for addr, s in enumerate(status):
            if s != STATUS_OK:
                sys.stdout.write(".. ")
            else:
                sys.stdout.write(f"{addr:02x} ")

            if (addr % 16) == 15:
                sys.stdout.write("\n")

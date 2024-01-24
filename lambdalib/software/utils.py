import sys

def hexdump(data):
    # return " ".join(["{:02x}".format(b) for b in data])

    sys.stdout.write("       ")
    for i in range(16):
        sys.stdout.write(hex(i)[2:])
        sys.stdout.write("  ")
    sys.stdout.write("\n0x00: ")

    for i, b in enumerate(data):
        sys.stdout.write(f"{b:02x} ")

        if (i % 16) == 15:
            sys.stdout.write("\n{}: ".format(hex(i+1)))

    sys.stdout.write("\n")

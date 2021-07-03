import sys


def debug(message):
    sys.stderr.write(f"{message}\n")


def debugnobreak(message):
    sys.stderr.write(message)

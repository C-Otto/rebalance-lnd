import sys

def debug(message):
    sys.stderr.write(message + "\n")

def debugnobreak(message):
    sys.stderr.write(message)
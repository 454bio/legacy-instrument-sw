class ZionProtocolVersionError(Exception):
    """An unsupported version of protcols."""
    pass

class ZionProtocolFileError(Exception):
    """A protocol JSON text file was in the wrong format."""
    pass

class ZionInvalidLEDPulsetime(Exception):
    """Invalid LED pulsetime"""
    pass

class ZionInvalidLEDMaxPulsetime(Exception):
    """Invalid LED pulsetime"""
    pass

class ZionInvalidLEDColor(Exception):
    """Invalid LED pulsetime"""
    pass

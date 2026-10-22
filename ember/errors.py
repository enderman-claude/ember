class CompileError(Exception):
    """A user-facing error in an Ember source file."""

    def __init__(self, line, msg, col=None):
        self.line = line
        self.col = col
        self.msg = msg
        loc = f"{line}" + (f":{col}" if col else "")
        super().__init__(f"line {loc}: {msg}")

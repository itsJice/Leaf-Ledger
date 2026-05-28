import io
import sys
from typing import Callable


class ForwardStream:
    def __init__(
        self,
        # A function taking (text)
        forward: Callable[[str], None],
        # Original stream to
        original_stream: io.IOBase | None,
    ):
        self.forward = forward
        self.original_stream = original_stream

    def write(self, s: str):
        if self.original_stream is not None:
            self.original_stream.write(s)
        self.forward(s)

    def flush(self):
        if self.original_stream is not None:
            self.original_stream.flush()


def install_logcapture(
    stdout_callback: Callable[[str], None],
    stderr_callback: Callable[[str], None],
):
    sys.stdout = ForwardStream(stdout_callback, sys.__stdout__)
    sys.stderr = ForwardStream(stderr_callback, sys.__stderr__)

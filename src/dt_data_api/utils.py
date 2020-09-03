import io
import math
import os
import time
from typing import Union, Iterator, BinaryIO, Optional, Callable
from types import SimpleNamespace
from functools import partial

from .constants import MAXIMUM_ALLOWED_SIZE


class TransferProgress(SimpleNamespace):

    def __init__(self, total: int, transferred: int, speed: int, part: int = 1, parts: int = 1):
        super(TransferProgress, self).__init__(
            total=total,
            transferred=transferred,
            speed=speed,
            part=part,
            parts=parts
        )

    def __str__(self):
        return super(TransferProgress, self).__str__()

    def __repr__(self):
        return super(TransferProgress, self).__repr__()


class IterableIO:

    def __init__(self, stream: Union[io.RawIOBase, BinaryIO], bufsize: int = 1024**2):
        self._stream = stream
        self._bufsize = bufsize

    def __iter__(self) -> Iterator[bytes]:
        buf = self._stream.read(self._bufsize)
        while len(buf):
            yield buf
            buf = self._stream.read(self._bufsize)


class RangedStream(io.RawIOBase):

    def __init__(self, stream, seek, limit):
        self._stream = stream
        self._seek = seek
        self._transferred = 0
        self._limit = limit
        self._initialized = False

    def close(self):
        return

    def read(self, size: int = ...) -> Optional[bytes]:
        if not self._initialized:
            self._stream.seek(self._seek)
            self._initialized = True
        size = min(size, self._limit - self._transferred)
        chunk = self._stream.read(size)
        self._transferred += len(chunk)
        return chunk


class MultipartBytesIO:

    def __init__(self, stream, stream_length, part_size: int = MAXIMUM_ALLOWED_SIZE):
        self._stream = stream
        self._stream_length = stream_length
        self._part_size = part_size
        self._start = 0

    def __iter__(self):
        for i in range(self.number_of_parts()):
            cursor = i * self._part_size
            part_length = min(self._stream_length - cursor, self._part_size)
            yield part_length, RangedStream(self._stream, cursor, self._part_size)

    def number_of_parts(self):
        return int(math.ceil(self._stream_length / self._part_size))


# class MultipartFileIO:
#
#     def __init__(self, fname, limit: int = MAXIMUM_ALLOWED_SIZE):
#         self._fname = fname
#         self._stream = open(self._fname, 'rb')
#         self._stream_length = os.path.getsize(self._fname)
#         self._limit = limit
#         self._start = 0
#
#     def __iter__(self):
#         for cursor in range(0, self._stream_length, self._limit):
#             self._stream.seek(cursor)
#             yield RangedStream(self._stream, self._limit)
#
#     def number_of_parts(self):
#         return int(math.ceil(self._stream_length / self._limit))


class MonitoredIOIterator:

    def __init__(self, iterator: Union[None, Iterator], total_bytes: int = -1,
                 callback: Callable = None):
        self._iterator = iterator
        self._total_bytes = total_bytes
        self._transferred_bytes = 0
        self._last_time = None
        self._callback = callback

    def set_iterator(self, iterator: Iterator):
        self._iterator = iterator

    def set_callback(self, callback: Callable):
        self._callback = callback

    def __iter__(self):
        return self

    def __next__(self):
        if self._iterator is None:
            raise StopIteration
        # ---
        data = next(self._iterator)
        self._transferred_bytes += len(data)
        # crate TransferProgress object
        progress = TransferProgress(
            self._total_bytes,
            self._transferred_bytes,
            0 if self._last_time is None else len(data) / (time.time() - self._last_time)
        )
        # update time
        self._last_time = time.time()
        # pass it to the callback
        if self._callback:
            self._callback(progress)
        # yield
        return data

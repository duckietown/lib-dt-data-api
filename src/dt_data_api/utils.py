import io
import math
import time
from threading import Thread
from typing import Union, Iterator, BinaryIO, Optional, Callable
from functools import partial

from .constants import MAXIMUM_ALLOWED_SIZE, TRANSFER_BUF_SIZE_B
from .exceptions import TransferAborted


class TransferProgress:

    def __init__(self, total: int, transferred: int = 0, part: int = 1, parts: int = 1):
        self._total = total
        self._transferred = transferred
        self._part = part
        self._parts = parts
        self._speed = 0
        self._last_update_time = None
        self._callbacks = set()

    @property
    def total(self) -> int:
        return self._total

    @property
    def transferred(self) -> int:
        return self._transferred

    @property
    def speed(self) -> float:
        return self._speed

    @property
    def part(self) -> int:
        return self._part

    @property
    def parts(self) -> int:
        return self._parts

    def register_callback(self, callback: Callable):
        self._callbacks.add(callback)

    def unregister_callback(self, callback: Callable):
        if callback in self._callbacks:
            self._callbacks.remove(callback)

    def update(self, total: int = None, transferred: int = None,
               part: int = None, parts: int = None):
        if total is not None:
            self._total = total
        # ---
        if transferred is not None:
            new_data_len = transferred - self._transferred
            if new_data_len > 0:
                now = time.time()
                if self._last_update_time is not None:
                    self._speed = new_data_len / (now - self._last_update_time)
                self._last_update_time = now
            self._transferred = transferred
        # ---
        if part is not None:
            self._part = part
        # ---
        if parts is not None:
            self._parts = parts
        # fire a new update event
        self._fire()

    def _fire(self):
        for callback in self._callbacks:
            callback(self)

    def __str__(self):
        return str({
            'total': self._total,
            'transferred': self._transferred,
            'speed': self._speed,
            'part': self._part,
            'parts': self._parts
        })


class WorkerThread(Thread):

    def __init__(self, job: Callable, *args, **kwargs):
        super(WorkerThread, self).__init__(*args, **kwargs)
        self._job = job
        self._is_shutdown = False
        setattr(self, 'run', partial(self._job, worker=self))

    @property
    def is_shutdown(self):
        return self._is_shutdown

    def shutdown(self):
        self._is_shutdown = True


class TransferHandler:

    def __init__(self, progress: TransferProgress):
        self._progress = progress
        self._workers = set()
        self._callbacks = set()
        # register the transfer handler as a progress callback
        self._progress.register_callback(self._fire)

    @property
    def progress(self):
        return self._progress

    def add_worker(self, worker: WorkerThread):
        self._workers.add(worker)

    def register_callback(self, callback: Callable):
        self._callbacks.add(callback)

    def unregister_callback(self, callback: Callable):
        if callback in self._callbacks:
            self._callbacks.remove(callback)

    def abort(self, block=False):
        # stop workers
        for worker in self._workers:
            if not worker.is_shutdown:
                worker.shutdown()
        # wait for workers to finish
        if block:
            for worker in self._workers:
                # noinspection PyBroadException
                try:
                    worker.join()
                except BaseException:
                    pass

    def _fire(self, *_, **__):
        for callback in self._callbacks:
            callback(self)

    def __str__(self):
        return str(self._progress)


class IterableIO:

    def __init__(self, stream: Union[io.RawIOBase, BinaryIO], bufsize: int = TRANSFER_BUF_SIZE_B):
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


class MonitoredIOIterator:

    def __init__(self, progress: TransferProgress,
                 iterator: Union[None, Iterator] = None, worker: Union[None, WorkerThread] = None):
        self._progress = progress
        self._iterator = iterator
        self._worker = worker
        self._transferred_bytes = 0
        self._last_time = None

    def set_iterator(self, iterator: Iterator):
        self._iterator = iterator

    def set_worker(self, worker: WorkerThread):
        self._worker = worker

    def __iter__(self):
        return self

    def __next__(self):
        if self._iterator is None:
            raise StopIteration()
        if self._worker.is_shutdown:
            raise TransferAborted()
        # ---
        data = next(self._iterator)
        self._transferred_bytes += len(data)
        # update progress handler
        self._progress.update(transferred=self._transferred_bytes)
        # update time
        self._last_time = time.time()
        # yield
        return data

import io
import math
import time
from enum import Enum
from threading import Thread
from typing import Union, Iterator, BinaryIO, Optional, Callable
from functools import partial

from .constants import MAXIMUM_ALLOWED_SIZE, TRANSFER_BUF_SIZE_B
from .exceptions import TransferAborted


class BytesBuffer(io.BytesIO):

    def fp(self):
        return self

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass


class WorkerThread(Thread):
    """
    Worker thread performing a generic `job`.

    Args:
        job:    A callable object expecting this `WorkerThread` object as first and sole argument.
        args:   Other positional arguments for the underlying :py:class:`threading.Thread` object.
        kwargs: Other named arguments for the underlying :py:class:`threading.Thread` object.
    """

    def __init__(self, job: Callable, *args, **kwargs):
        super(WorkerThread, self).__init__(*args, **kwargs)
        self._job = job
        self._is_shutdown = False
        setattr(self, "run", partial(self._job, worker=self))

    @property
    def is_shutdown(self) -> bool:
        """
        Whether the worker is interrupted.
        """
        return self._is_shutdown

    def shutdown(self):
        """
        Interrupts the worker.
        """
        self._is_shutdown = True


class TransferStatus(Enum):
    """
    Models the status of a transfer operation.

    UNKNOWN:
        Unknown status.

    READY:
        Transfer is ready but has not started yet.

    ACTIVE:
        Transfer is currently active. Data is flowing.

    STOPPED:
        The transfer was stopped before the end.

    FINISHED:
        The transfer successfully finished.

    ERROR:
        An error occurred and the transfer was interrupted.
    """

    UNKNOWN = 0
    READY = 1
    ACTIVE = 10
    STOPPED = 20
    FINISHED = 30
    ERROR = 90


class TransferProgress:
    """
    Models the progress of a transfer operation.

    Args:
        total:          Total number of bytes to transfer.
        transferred:    Number of bytes transferred so far.
        part:           Number of the part being transferred.
        parts:          Total number of parts to transfer.
    """

    def __init__(self, total: int, transferred: int = 0, part: int = 1, parts: int = 1):
        self._total = total
        self._transferred = transferred
        self._part = part
        self._parts = parts
        self._speed = 0
        self._percentage = 0
        self._last_update_time = None
        self._callbacks = set()

    @property
    def total(self) -> int:
        """
        Total number of bytes to transfer.
        """
        return self._total

    @property
    def transferred(self) -> int:
        """
        Number of bytes transferred so far.
        """
        return self._transferred

    @property
    def speed(self) -> float:
        """
        Current transfer speed in `bytes/sec`.
        """
        return self._speed

    @property
    def percentage(self) -> float:
        """
        Current progress in percentage.
        """
        return self._percentage

    @property
    def part(self) -> int:
        """
        Number of the part being transferred.
        """
        return self._part

    @property
    def parts(self) -> int:
        """
        Total number of parts to transfer.
        """
        return self._parts

    def register_callback(self, callback: Callable):
        """
        Registers a callback function that will be called every time an update to the progress
        is available.

        Args:
            callback:   A callable object expecting this `TransferProgress` object as first and
                        sole argument.
        """
        self._callbacks.add(callback)

    def unregister_callback(self, callback: Callable):
        """
        Unregisters a callback function previously registered.

        Args:
            callback:   A callable object.
        """
        if callback in self._callbacks:
            self._callbacks.remove(callback)

    def update(self, total: int = None, transferred: int = None, part: int = None,
               parts: int = None):
        """
        Updates the internal state of the object.

        Args:
            total:          (Optional) Total number of bytes to transfer.
            transferred:    (Optional) Number of bytes transferred so far.
            part:           (Optional) Number of the part being transferred.
            parts:          (Optional) Total number of parts to transfer.
        """
        if total is not None:
            self._total = total
        # ---
        if transferred is not None:
            new_data_len = transferred - self._transferred
            # compute speed
            if new_data_len > 0:
                now = time.time()
                if self._last_update_time is not None:
                    self._speed = new_data_len / (now - self._last_update_time)
                self._last_update_time = now
            # compute percentage
            self._percentage = math.floor(100 * transferred / self._total) if self._total else 0
            # update transferred
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
        """
        Fires an update event to the registered callbacks.
        """
        for callback in self._callbacks:
            callback(self)

    def __str__(self):
        """
        Stringifies the object.
        """
        return str(
            {
                "total": self._total,
                "transferred": self._transferred,
                "speed": self._speed,
                "percentage": self._percentage,
                "part": self._part,
                "parts": self._parts,
            }
        )


class TransferHandler:
    """
    Models a transfer operation.

    Args:
        progress:   The progress monitor for this transfer operation.
    """

    def __init__(self, progress: TransferProgress):
        self._progress = progress
        self._buffer: Optional[io.BytesIO] = None
        self._status = TransferStatus.UNKNOWN
        self._reason = "(none)"
        self._workers = set()
        self._callbacks = set()
        # register the transfer handler as a progress callback
        self._progress.register_callback(self._fire)

    @property
    def status(self) -> TransferStatus:
        """
        The current status of this transfer operation.
        """
        return self._status

    @property
    def data(self) -> Optional[bytes]:
        """
        The content of the buffer where the download happens.
        """
        if self._buffer is not None:
            return self._buffer.getvalue()
        return None

    @property
    def buffer(self) -> Optional[io.BytesIO]:
        """
        The buffer where the download happens.
        """
        return self._buffer

    @buffer.setter
    def buffer(self, buffer: BytesBuffer):
        """
        Sets pointer to internal buffer where the download happens.

        Args:
            buffer: Download buffer.
        """
        if not isinstance(buffer, BytesBuffer):
            raise ValueError(
                f"Expected `buffer` of type `BytesBuffer`. "
                f"Got `{str(type(buffer))}` instead."
            )
        self._buffer = buffer

    @status.setter
    def status(self, new_status: TransferStatus):
        """
        Sets new transfer status.

        Args:
            new_status: New status.
        """
        if not isinstance(new_status, TransferStatus):
            raise ValueError(
                f"Expected `new_status` of type `TransferStatus`. " 
                f"Got `{str(type(new_status))}` instead."
            )
        self._status = new_status

    @property
    def progress(self) -> TransferProgress:
        """
        The progress monitor for this transfer operation.
        """
        return self._progress

    @property
    def reason(self) -> str:
        """
        A textual description of why the transfer is in the current status.
        For example, when the status is `ERROR`, this carries an error message.
        """
        return self._reason

    def set_status(self, new_status: TransferStatus, reason: str):
        """
        Sets transfer status and relative reason.

        Args:
            new_status: New status.
            reason:     A description of what triggered this change in status.
        """
        self.status = new_status
        self._reason = reason

    def add_worker(self, worker: WorkerThread):
        """
        Adds a worker to this tranfer operation.

        Args:
            worker: A worker thread object performing a job relative to this transfer operation.
        """
        self._workers.add(worker)

    def register_callback(self, callback: Callable):
        """
        Registers a callback function for updates.

        Args:
            callback:   A callable object expecting this `TransferHandler` object as first and
                        sole argument.
        """
        self._callbacks.add(callback)

    def unregister_callback(self, callback: Callable):
        """
        Unregisters a callback function previously registered.

        Args:
            callback:   A callable object.
        """
        if callback in self._callbacks:
            self._callbacks.remove(callback)

    def abort(self, block: bool = False):
        """
        Aborts the transfer operation.

        Args:
            block:  Whether to block until all jobs associates to this tranfer are fully stopped.
        """
        # stop workers
        for worker in self._workers:
            if not worker.is_shutdown:
                worker.shutdown()
        # wait for workers to finish
        if block:
            self.join()

    def join(self):
        """
        Blocks until the operation is completed.
        """
        for worker in self._workers:
            # noinspection PyBroadException
            try:
                worker.join()
            except BaseException:
                pass

    def _fire(self, *_, **__):
        """
        Fires an update event to the registered callbacks.
        """
        for callback in self._callbacks:
            callback(self)

    def __str__(self):
        """
        Stringifies the object.
        """
        return str(self._progress)


class IterableIO:
    """
    A converter object turning a file-like object into an iterator of chunks of bytes.

    Args:
        stream:     Underlying stream to consume.
        bufsize:    Buffer size in number of `bytes`. Each chunk will have at most this size.
    """

    def __init__(self, stream: Union[io.RawIOBase, BinaryIO], bufsize: int = TRANSFER_BUF_SIZE_B):
        self._stream = stream
        self._bufsize = bufsize

    def __iter__(self) -> Iterator[bytes]:
        """
        Iterator of chunks of bytes.
        """
        buf = self._stream.read(self._bufsize)
        while len(buf):
            yield buf
            buf = self._stream.read(self._bufsize)


class RangedStream(io.RawIOBase):
    """
    Masked file-like object that consumes bytes from the region [`seek`, `seek+limit`] of
    the underlying file-like object `stream`.

    Args:
        stream: Underlying file-like object to consume.
        seek:   Position of the first byte to consume from `stream`.
        limit:  Total number of bytes to consume from `stream`.
    """

    def __init__(self, stream: io.RawIOBase, seek: int, limit: int):
        self._stream = stream
        self._seek = seek
        self._transferred = 0
        self._limit = limit
        self._initialized = False

    def close(self):
        """
        Closes the stream.
        """
        return

    def read(self, size: int = ...) -> Optional[bytes]:
        """
        Reads a chunk of bytes of size at most `size`.

        Args:
            size:   Maximum size of bytes to read at once.

        Returns:
            bytes:  Chunk of bytes.
        """
        if not self._initialized:
            self._stream.seek(self._seek)
            self._initialized = True
        size = min(size, self._limit - self._transferred)
        chunk = self._stream.read(size)
        self._transferred += len(chunk)
        return chunk


class MultipartBytesIO:
    """
    Splitter of large stream of bytes.

    Args:
        stream:     Underlying file-like object.
        length:     Length of the stream.
        part_size:  Size of each block in the partition.
    """

    def __init__(self, stream: io.RawIOBase, length: int, part_size: int = MAXIMUM_ALLOWED_SIZE):
        self._stream = stream
        self._stream_length = length
        self._part_size = part_size
        self._start = 0

    def __iter__(self) -> Iterator[RangedStream]:
        """
        Iterator of `RangedStream` object.
        """
        for i in range(self.number_of_parts()):
            cursor = i * self._part_size
            part_length = min(self._stream_length - cursor, self._part_size)
            yield part_length, RangedStream(self._stream, cursor, self._part_size)

    def number_of_parts(self) -> int:
        """
        Number of parts (partition blocks).

        Returns:
            int:    Number of parts produced by this splitter.
        """
        return int(math.ceil(self._stream_length / self._part_size))


class MonitoredIOIterator:
    """
    Monitored file-like object.
    Consumes an iterator of bytes and updates a TransferProgress object.

    Args:
        progress:   Instance of :py:class:`TransferProgress` to update.
        iterator:   Iterator of bytes to consume.
        worker:     Instance of :py:class:`WorkerThread` performing the transfer job.
    """

    def __init__(
        self,
        progress: TransferProgress,
        iterator: Union[None, Iterator[bytes]] = None,
        worker: Union[None, WorkerThread] = None,
    ):
        self._progress = progress
        self._iterator = iterator
        self._worker = worker
        self._transferred_bytes = 0
        self._last_time = None

    def set_iterator(self, iterator: Iterator[bytes]):
        """
        Updates the underlying iterator of bytes to consume data from.

        Args:
            iterator:   Iterator of bytes to consume.
        """
        self._iterator = iterator

    def set_worker(self, worker: WorkerThread):
        """
        Sets the current worker thread.

        Args:
            worker: Worker thread.
        """
        self._worker = worker

    def __iter__(self):
        """
        Activates a proxy iterator
        """
        return self

    def __next__(self) -> bytes:
        """
        Next element from the iterator.

        Returns:
            bytes:  Chunk of bytes from the underlying iterator.

        Raises:
            StopIteration:      End of the iterator reached.
            TransferAborted:    The worker was interrupted.
        """
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

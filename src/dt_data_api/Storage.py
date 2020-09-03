import os
import io
import time
from functools import partial
from typing import Union, BinaryIO, Callable
import requests

from .API import DataAPI
from .utils import IterableIO, MonitoredIOIterator, MultipartBytesIO, TransferProgress
from .constants import BUCKET_NAME, PUBLIC_STORAGE_URL
from .exceptions import TransferError


def _callback(progress, cb=None, part=1, parts=1):
    if cb is None:
        return
    progress.part = part
    progress.parts = parts
    cb(progress)


class Storage(object):

    def __init__(self, api: DataAPI, name: str):
        self._api = api
        self._name = name
        self._full_name = BUCKET_NAME.format(name=name)

    def head(self, obj):
        if self._name == 'public':
            # anybody can do this
            url = PUBLIC_STORAGE_URL.format(bucket=self._name, object=obj)
        else:
            # you need permission for this, authorize request
            url = self._api.authorize_request('head_object', self._full_name, obj)
        # send request
        try:
            res = requests.head(url)
        except requests.exceptions.ConnectionError as e:
            raise TransferError()
        # check output
        if res.status_code == 404:
            raise FileNotFoundError(f"Object '{obj}' not found")
        # ---
        return res.headers

    def download(self, source: str, destination: str, force: bool = False,
                 callback: Callable = None):
        parts = self._get_parts(source)
        # check destination
        if os.path.exists(destination):
            if os.path.isdir(destination):
                raise ValueError(f"The path '{destination}' already exists and is a directory.")
            if not force:
                raise ValueError(f"The destination file '{destination}' already exists. Use "
                                 f"`force=True` to overwrite it.")
        # get parts metadata
        metas = [self.head(part) for part in parts]
        obj_length = sum([int(r['Content-Length']) for r in metas])
        # open destination
        dest_length = 0
        last_time = None
        with open(destination, 'wb') as fout:
            # download parts
            for i, part in enumerate(parts):
                # ---
                if self._name == 'public':
                    # anybody can do this
                    url = PUBLIC_STORAGE_URL.format(bucket=self._name, object=part)
                else:
                    # you need permission for this, authorize request
                    url = self._api.authorize_request('get_object', self._full_name, part)
                # send request
                res = requests.get(url, stream=True)
                # stream content
                for chunk in res.iter_content(1024**2):
                    fout.write(chunk)
                    dest_length += len(chunk)
                    speed = 0 if last_time is None else len(chunk) / (time.time() - last_time)
                    if callback:
                        callback(TransferProgress(obj_length, dest_length, speed, i, len(parts)))
                    last_time = time.time()

    def upload(self, source: Union[str, bytes, BinaryIO], destination: str, length: int = None,
               callback: Callable = None):
        if isinstance(source, str):
            file_path = os.path.abspath(source)
            if not os.path.isfile(file_path):
                raise ValueError(f'The file {file_path} does not exist.')
            source = open(file_path, 'rb')
            source_len = os.path.getsize(file_path)
        elif isinstance(source, bytes):
            source_len = len(source)
            source = io.BytesIO(source)
        elif isinstance(source, io.RawIOBase):
            if length is None or 0 < length:
                raise ValueError('When `source` is a file-like object, the stream `length` '
                                 'must be explicitly provided (as number of bytes).')
            source_len = length
        else:
            raise ValueError(f'Source object must be either a string (file path), a bytes object '
                             f'or a binary stream, got {str(type(source))} instead.')
        # ---
        # create a multipart handler
        parts = MultipartBytesIO(source, source_len, part_size=10 * 1024**2)
        num_parts = parts.number_of_parts()
        # create a monitored iterator
        monitor = MonitoredIOIterator(None, source_len)
        # sanitize destination
        destination = destination.lstrip('/')
        # create destination format
        destination_fmt = lambda p: \
            destination + (f'.{p:03d}' if num_parts > 1 else '')
        # iterate over the parts
        for part, (stream_len, stream) in enumerate(parts):
            print(f'part {part+1}/{num_parts} has size {stream_len}')
            dest_part = destination_fmt(part)
            monitor.set_iterator(iter(IterableIO(stream)))
            # create a callback
            decorated_cb = partial(_callback, cb=callback, parts=num_parts, part=part+1)
            monitor.set_callback(decorated_cb)
            # round up metadata
            metadata = {
                'x-amz-meta-number-of-parts': str(num_parts)
            }
            # authorize request
            url = self._api.authorize_request(
                'put_object', self._full_name, dest_part, headers=metadata)
            # prepare request
            req = requests.Request('PUT', url, data=monitor).prepare()
            # remove header 'Transfer-Encoding'
            del req.headers['Transfer-Encoding']
            # add header 'Content-Length'
            req.headers['Content-Length'] = stream_len
            # add metadata
            req.headers.update(metadata)
            # send request
            try:
                res = requests.Session().send(req)
            except requests.exceptions.ConnectionError as e:
                raise TransferError()
            # parse response
            if res.status_code != 200:
                raise TransferError(f'Transfer Error: Code: {res.status_code} Message: {res.text}')

    def _get_parts(self, obj: str):
        modes = [
            (False, obj,          lambda _: obj),
            (True,  obj + '.000', lambda p: obj + f'.{p:03d}'),
        ]
        for multipart, source, part_name in modes:
            try:
                res = self.head(source)
                parts = int(res.get('x-amz-meta-number-of-parts', '1'))
                return [obj] if not multipart else [part_name(p) for p in range(parts)]
            except FileNotFoundError:
                pass
        raise FileNotFoundError(f"Object '{obj}' not found")
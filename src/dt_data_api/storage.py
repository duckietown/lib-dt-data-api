import os
import io
from functools import partial

import requests
from bs4 import BeautifulSoup

from typing import Union, BinaryIO, Dict, List, Optional

from dt_authentication import DuckietownToken

from . import logger
from .api import DataAPI
from .utils import (
    IterableIO,
    MonitoredIOIterator,
    MultipartBytesIO,
    TransferProgress,
    WorkerThread,
    TransferHandler,
    TransferStatus,
    BytesBuffer)
from .constants import BUCKET_NAME, PUBLIC_STORAGE_URL, TRANSFER_BUF_SIZE_B
from .exceptions import TransferError, TransferAborted, APIError


class Storage(object):
    """
    Provides an interface to a storage space on the DCSS.

    .. warning::
        You should not create instances of this class yourself. Use the method
        :py:meth:`dt_data_api.DataClient.storage` instead.

    Args:
        api:    An instance of :py:class:`dt_data_api.api.DataAPI` used to communicate with the
                RESTful Data API.
        name:   Name of the storage space to connect to.
    """

    def __init__(self, api: DataAPI, name: str):
        self._api = api
        self._name = name
        self._full_name = BUCKET_NAME.format(name=name)

    @property
    def api(self) -> DataAPI:
        """ The low-level API object used to communicate with the DCSS """
        return self._api

    def list_objects(self, prefix: str) -> List[str]:
        """
        Lists objects starting with a given prefix.

        Args:
            prefix:         The path prefix to start listing from.

        Returns:
            list[str]:      A list of keys identifying the objects.

        Raises:
            dt_data_api.TransferError:  An error occurs while transferring the data from the DCSS.
            dt_data_api.APIError:       An error occurs while communicating with the DCSS.

        """
        prefix = self._sanitize_remote_path(prefix)
        # authorize request
        self._check_token(f"Storage[{self._name}].list_objects_v2(...)")
        url = self._api.authorize_request("list_objects_v2", self._full_name, prefix)
        # send request
        try:
            res = requests.get(url)
        except requests.exceptions.ConnectionError as e:
            raise TransferError(e)
        # parse output
        items = []
        soup = BeautifulSoup(res.text, 'xml')
        for item in soup.find_all('Contents'):
            items.append(item.Key.text)
        # ---
        return items

    def head(self, obj: str) -> Dict[str, str]:
        """
        Retrieves metadata about the object `obj`.

        Args:
            obj:    The object to retrieve the metadata for.

        Returns:
            dict[str, str]:     A key-value mapping containing the metadata.

        Raises:
            FileNotFoundError:          The object was not found in the storage space.
            dt_data_api.TransferError:  An error occurs while transferring the data from the DCSS.
            dt_data_api.APIError:       An error occurs while communicating with the DCSS.

        """
        obj = self._sanitize_remote_path(obj)
        if self._name == "public":
            # anybody can do this
            url = PUBLIC_STORAGE_URL.format(bucket=self._name, object=obj)
        else:
            # you need permission for this, authorize request
            self._check_token(f"Storage[{self._name}].head(...)")
            url = self._api.authorize_request("head_object", self._full_name, obj)
        # send request
        try:
            res = requests.head(url)
        except requests.exceptions.ConnectionError as e:
            raise TransferError(e)
        # check output
        if res.status_code == 404:
            raise FileNotFoundError(f"Object '{obj}' not found")
        # ---
        return dict(res.headers)

    def download(self, source: str, destination: Optional[str] = None,
                 force: bool = False) -> TransferHandler:
        """
        Downloads a file from the storage space.

        Args:
            source:         The path to the file to download in the storage space.
            destination:    The local path the file is downloaded to.
            force:          Whether the destination file is overwritten in case it exists.

        Returns:
            TransferHandler:    An handler to the transfer operation.

        Raises:
            ValueError:                 One of the arguments has an illegal value.
            FileNotFoundError:          The object was not found in the storage space.
            dt_data_api.TransferError:  An error occurs while transferring the data from the DCSS.

        """
        source = self._sanitize_remote_path(source)
        parts = self._get_parts(source)
        to_disk = isinstance(destination, str)
        if not to_disk:
            destination = BytesBuffer()
        # check destination
        if to_disk and os.path.exists(destination):
            if os.path.isdir(destination):
                raise ValueError(f"The path '{destination}' already exists and is a directory.")
            if not force:
                raise ValueError(
                    f"The destination file '{destination}' already exists. Use "
                    f"`force=True` to overwrite it."
                )
        # get parts metadata
        metas = [self.head(part) for part in parts]
        obj_length = sum([int(r["Content-Length"]) for r in metas])
        # create a transfer handler
        progress = TransferProgress(obj_length, parts=len(parts))
        handler = TransferHandler(progress)
        if not to_disk:
            handler.buffer = destination
        # set status to READY
        handler.set_status(TransferStatus.READY, "Worker created")
        # create fp object
        fp = partial(open, destination, "wb") if to_disk else destination.fp

        # clean up job
        def clean_up():
            if to_disk and os.path.exists(destination) and os.path.isfile(destination):
                os.remove(destination)
            if not to_disk:
                destination.truncate(0)

        # define downloading job
        def job(worker: WorkerThread, *_, **__):
            # set status to ACTIVE
            handler.set_status(TransferStatus.ACTIVE, "Worker started")
            # open destination
            with fp() as fout:
                # download parts
                for i, part in enumerate(parts):
                    # check worker
                    if worker.is_shutdown:
                        logger.debug("Transfer aborted!")
                        # set status to STOPPED
                        handler.set_status(TransferStatus.STOPPED, "Worker was stopped")
                        # clean up partial files
                        clean_up()
                        # tell the server we are done
                        res.close()
                        # get out of here
                        return
                    # ---
                    # update progress
                    progress.update(part=i + 1)
                    # get url to part
                    if self._name == "public":
                        # anybody can do this
                        url = PUBLIC_STORAGE_URL.format(bucket=self._name, object=part)
                    else:
                        # you need permission for this, authorize request
                        self._check_token(f"Storage[{self._name}].download(...)")
                        try:
                            url = self._api.authorize_request("get_object", self._full_name, part)
                        except APIError as e:
                            # set status to ERROR
                            handler.set_status(TransferStatus.ERROR, str(e))
                            return
                    # send request
                    res = requests.get(url, stream=True)
                    # stream content
                    for chunk in res.iter_content(TRANSFER_BUF_SIZE_B):
                        # check worker
                        if worker.is_shutdown:
                            logger.debug("Transfer aborted!")
                            # set status to STOPPED
                            handler.set_status(TransferStatus.STOPPED, "Worker was stopped")
                            # clean up partial files
                            clean_up()
                            # tell the server we are done
                            res.close()
                            # get out of here
                            return
                        # ---
                        fout.write(chunk)
                        # update progress
                        progress.update(transferred=progress.transferred + len(chunk))

        # create a worker
        worker_th = WorkerThread(job)
        # register worker with the handler
        handler.add_worker(worker_th)
        # start the worker
        worker_th.start()
        # return transfer handler
        return handler

    def upload(
        self, source: Union[str, bytes, BinaryIO], destination: str, length: int = None
    ) -> TransferHandler:
        """
        Uploads a file to the storage space.

        Args:
            source:         `str` - The local path of the file to upload.\n
                            `bytes` - Content of the file as `bytes` object.\n
                            `BinaryIO` - A file-like object.
            destination:    The path to the resulting file in the storage space.
            length:         (Optional) Length of the data in bytes. Only needed when `source`
                            is of type `BinaryIO`.

        Returns:
            TransferHandler:    An handler to the transfer operation.

        Raises:
            ValueError:                 One of the arguments has an illegal value.
            dt_data_api.TransferError:  An error occurs while transferring the data to the DCSS.

        """
        if isinstance(source, str):
            file_path = os.path.abspath(source)
            if not os.path.isfile(file_path):
                raise ValueError(f"The file {file_path} does not exist.")
            source = open(file_path, "rb")
            source_len = os.path.getsize(file_path)
        elif isinstance(source, bytes):
            source_len = len(source)
            source = io.BytesIO(source)
        elif isinstance(source, io.RawIOBase):
            if length is None or 0 < length:
                raise ValueError(
                    "When `source` is a file-like object, the stream `length` "
                    "must be explicitly provided (as number of bytes)."
                )
            source_len = length
        else:
            raise ValueError(
                f"Source object must be either a string (file path), a bytes object "
                f"or a binary stream, got {str(type(source))} instead."
            )
        # prepare owner information
        owner = {"id": "0"}
        if self._api.token is not None:
            token = DuckietownToken.from_string(self._api.token)
            owner["id"] = str(token.uid)
        # ---
        # create a multipart handler
        parts = MultipartBytesIO(source, source_len)
        num_parts = parts.number_of_parts()
        # create a transfer progress handler
        progress = TransferProgress(total=source_len, parts=num_parts)
        # create a transfer handler
        handler = TransferHandler(progress)
        # create a monitored iterator
        monitor = MonitoredIOIterator(progress)
        # sanitize destination
        destination = self._sanitize_remote_path(destination)
        # create destination format
        destination_fmt = lambda p: destination + (f".{p:03d}" if num_parts > 1 else "")
        # set status to READY
        handler.set_status(TransferStatus.READY, "Worker created")

        # define uploading job
        def job(worker: WorkerThread, *_, **__):
            # set status to ACTIVE
            handler.set_status(TransferStatus.ACTIVE, "Worker started")
            # iterate over the parts
            for part, (stream_len, stream) in enumerate(parts):
                if worker.is_shutdown:
                    logger.debug("Transfer aborted!")
                    return
                # ---
                dest_part = destination_fmt(part)
                monitor.set_iterator(iter(IterableIO(stream)))
                # update progress
                progress.update(part=part + 1)
                # round up metadata
                metadata = {
                    "x-amz-meta-number-of-parts": str(num_parts),
                    **{f"x-amz-meta-owner-{k}": v for k, v in owner.items()},
                }
                # authorize request
                self._check_token(f"Storage[{self._name}].upload(...)")
                try:
                    url = self._api.authorize_request(
                        "put_object", self._full_name, dest_part, headers=metadata
                    )
                except APIError as e:
                    # set status to ERROR
                    handler.set_status(TransferStatus.ERROR, str(e))
                    return
                # prepare request
                req = requests.Request("PUT", url, data=monitor).prepare()
                # remove header 'Transfer-Encoding'
                del req.headers["Transfer-Encoding"]
                # add header 'Content-Length'
                req.headers["Content-Length"] = stream_len
                # add metadata
                req.headers.update(metadata)
                # send request
                try:
                    # open a session
                    session = requests.Session()
                    # send request through the session
                    res = session.send(req)
                except requests.exceptions.ConnectionError as e:
                    # set status to ERROR
                    handler.set_status(TransferStatus.ERROR, str(e))
                    logger.debug(f"ERROR: {str(e)}")
                    return
                except TransferAborted:
                    # set status to ERROR
                    handler.set_status(TransferStatus.STOPPED, "Worker was stopped")
                    logger.debug("Worker was stopped!")
                    return
                # parse response
                if res.status_code != 200:
                    # set status to ERROR
                    handler.set_status(TransferStatus.ERROR, res.text)
                    logger.debug(f"Transfer Error: Code: {res.status_code} Message: {res.text}")
                    return
                # set status to FINISHED
                handler.set_status(TransferStatus.FINISHED, "Finished")

        # create a worker
        worker_th = WorkerThread(job)
        # register worker with the handler
        handler.add_worker(worker_th)
        # give the worker to the iterator monitor so that the flow of data can be interrupted
        # when the worker is stopped
        monitor.set_worker(worker_th)
        # start the worker
        worker_th.start()
        # return transfer handler
        return handler

    def _sanitize_remote_path(self, path: str) -> str:
        """
        Sanitizes a remote path for this storage space.

        Args:
            path:           `str` - Path to sanitize.

        Returns:
            str:            Sanitized path.
        """
        return path.lstrip("/")

    def _get_parts(self, obj: str):
        """
        Returns a list of parts to download and append together to form the complete file.

        Args:
            obj:    The path to the object in the storage space.

        Raises:
            FileNotFoundError:  The object was not found in the storage space.

        """
        modes = [
            (False, obj, lambda _: obj),
            (True, obj + ".000", lambda p: obj + f".{p:03d}"),
        ]
        for multipart, source, part_name in modes:
            try:
                res = self.head(source)
                parts = int(res.get("x-amz-meta-number-of-parts", "1"))
                return [obj] if not multipart else [part_name(p) for p in range(parts)]
            except FileNotFoundError:
                pass
        raise FileNotFoundError(f"Object '{obj}' not found")

    def _check_token(self, resource: str = None):
        """
        Checks if the token was set inside the DataClient object.

        Args:
            resource:   (Optional)  A brief description of the service needing the token.

        Raises:
            ValueError:     The token was not set (i.e., the client is unathenticated).
        """
        if self._api.token is None:
            resource = "This resource" if not resource else f"The resource {resource}"
            raise ValueError(
                f"{resource} requires a valid token. Initialize the DataClient "
                f"object with the `token` argument set."
            )


class UserStorage(Storage):
    """
    Provides an interface to a user's private space on the DCSS.

    .. warning::
        You should not create instances of this class yourself. Use the method
        :py:meth:`dt_data_api.DataClient.storage` and pass the argument `"user"` instead.

    Args:
        api:            An instance of DataAPI used to communicate with the RESTful Data API.
        name:           Name of the storage space to connect to.
        impersonate:
    """

    def __init__(self, api: DataAPI, name: str, impersonate: Union[None, int] = None):
        super().__init__(api, name)
        self._impersonate = impersonate

    def _sanitize_remote_path(self, path: str) -> str:
        """
        Sanitizes a remote path for this storage space.

        Args:
            path:           `str` - Path to sanitize.

        Returns:
            str:            Sanitized path.
        """
        path = super(UserStorage, self)._sanitize_remote_path(path)
        uid = self._impersonate or self._api.uid
        user_dir = f"{uid}/"
        if not path.startswith(user_dir):
            path = os.path.join(user_dir, path)
        return path

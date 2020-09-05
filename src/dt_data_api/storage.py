import os
import io
from typing import Union, BinaryIO
import requests

from . import logger
from .api import DataAPI
from .utils import IterableIO, MonitoredIOIterator, MultipartBytesIO, TransferProgress, \
    WorkerThread, TransferHandler
from .constants import BUCKET_NAME, PUBLIC_STORAGE_URL, TRANSFER_BUF_SIZE_B
from .exceptions import TransferError, TransferAborted


class Storage(object):
    """
    The ``LineDetectorNode`` is responsible for detecting the line white, yellow and red line segment in an image and
    is used for lane localization.

    Upon receiving an image, this node reduces its resolution, cuts off the top part so that only the
    road-containing part of the image is left, extracts the white, red, and yellow segments and publishes them.
    The main functionality of this node is implemented in the :py:class:`line_detector.LineDetector` class.

    The performance of this node can be very sensitive to its configuration parameters. Therefore, it also provides a
    number of debug topics which can be used for fine-tuning these parameters. These configuration parameters can be
    changed dynamically while the node is running via ``rosparam set`` commands.

    Args:
        node_name (:obj:`str`): a unique, descriptive name for the node that ROS will use

    Configuration:
        ~line_detector_parameters (:obj:`dict`): A dictionary with the parameters for the detector. The full list can be found in :py:class:`line_detector.LineDetector`.
        ~colors (:obj:`dict`): A dictionary of colors and color ranges to be detected in the image. The keys (color names) should match the ones in the Segment message definition, otherwise an exception will be thrown! See the ``config`` directory in the node code for the default ranges.
        ~img_size (:obj:`list` of ``int``): The desired downsized resolution of the image. Lower resolution would result in faster detection but lower performance, default is ``[120,160]``
        ~top_cutoff (:obj:`int`): The number of rows to be removed from the top of the image _after_ resizing, default is 40

    Subscriber:
        ~camera_node/image/compressed (:obj:`sensor_msgs.msg.CompressedImage`): The camera images
        ~anti_instagram_node/thresholds(:obj:`duckietown_msgs.msg.AntiInstagramThresholds`): The thresholds to do color correction

    Publishers:
        ~segment_list (:obj:`duckietown_msgs.msg.SegmentList`): A list of the detected segments. Each segment is an :obj:`duckietown_msgs.msg.Segment` message
        ~debug/segments/compressed (:obj:`sensor_msgs.msg.CompressedImage`): Debug topic with the segments drawn on the input image
        ~debug/edges/compressed (:obj:`sensor_msgs.msg.CompressedImage`): Debug topic with the Canny edges drawn on the input image
        ~debug/maps/compressed (:obj:`sensor_msgs.msg.CompressedImage`): Debug topic with the regions falling in each color range drawn on the input image
        ~debug/ranges_HS (:obj:`sensor_msgs.msg.Image`): Debug topic with a histogram of the colors in the input image and the color ranges, Hue-Saturation projection
        ~debug/ranges_SV (:obj:`sensor_msgs.msg.Image`): Debug topic with a histogram of the colors in the input image and the color ranges, Saturation-Value projection
        ~debug/ranges_HV (:obj:`sensor_msgs.msg.Image`): Debug topic with a histogram of the colors in the input image and the color ranges, Hue-Value projection

    """

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
            self._check_token(f'Storage[{self._name}].head(...)')
            url = self._api.authorize_request('head_object', self._full_name, obj)
        # send request
        try:
            res = requests.head(url)
        except requests.exceptions.ConnectionError as e:
            raise TransferError(e)
        # check output
        if res.status_code == 404:
            raise FileNotFoundError(f"Object '{obj}' not found")
        # ---
        return res.headers

    def download(self, source: str, destination: str, force: bool = False):
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
        # create a transfer handler
        progress = TransferProgress(obj_length, parts=len(parts))
        handler = TransferHandler(progress)

        # define downloading job
        def job(worker: WorkerThread, *_, **__):
            # open destination
            with open(destination, 'wb') as fout:
                # download parts
                for i, part in enumerate(parts):
                    # check worker
                    if worker.is_shutdown:
                        logger.debug('Transfer aborted!')
                        return
                    # ---
                    # update progress
                    progress.update(part=i + 1)
                    # get url to part
                    if self._name == 'public':
                        # anybody can do this
                        url = PUBLIC_STORAGE_URL.format(bucket=self._name, object=part)
                    else:
                        # you need permission for this, authorize request
                        self._check_token(f'Storage[{self._name}].download(...)')
                        url = self._api.authorize_request('get_object', self._full_name, part)
                    # send request
                    res = requests.get(url, stream=True)
                    # stream content
                    for chunk in res.iter_content(TRANSFER_BUF_SIZE_B):
                        # check worker
                        if worker.is_shutdown:
                            logger.debug('Transfer aborted!')
                            res.close()
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

    def upload(self, source: Union[str, bytes, BinaryIO], destination: str, length: int = None):
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
        parts = MultipartBytesIO(source, source_len)
        num_parts = parts.number_of_parts()
        # create a transfer progress handler
        progress = TransferProgress(total=source_len, parts=num_parts)
        # create a transfer handler
        handler = TransferHandler(progress)
        # create a monitored iterator
        monitor = MonitoredIOIterator(progress)
        # sanitize destination
        destination = destination.lstrip('/')
        # create destination format
        destination_fmt = lambda p: \
            destination + (f'.{p:03d}' if num_parts > 1 else '')

        # define uploading job
        def job(worker: WorkerThread, *_, **__):
            # iterate over the parts
            for part, (stream_len, stream) in enumerate(parts):
                if worker.is_shutdown:
                    logger.debug('Transfer aborted!')
                    return
                # ---
                dest_part = destination_fmt(part)
                monitor.set_iterator(iter(IterableIO(stream)))
                # update progress
                progress.update(part=part + 1)
                # round up metadata
                metadata = {
                    'x-amz-meta-number-of-parts': str(num_parts)
                }
                # authorize request
                self._check_token(f'Storage[{self._name}].upload(...)')
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
                    # open a session
                    session = requests.Session()
                    # send request through the session
                    res = session.send(req)
                except requests.exceptions.ConnectionError as e:
                    raise TransferError(e)
                except TransferAborted:
                    logger.debug('Transfer aborted!')
                    return
                # parse response
                if res.status_code != 200:
                    raise TransferError(
                        f'Transfer Error: Code: {res.status_code} Message: {res.text}')

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

    def _get_parts(self, obj: str):
        modes = [
            (False,          obj, lambda _: obj),
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

    def _check_token(self, resource=None):
        if self._api.token is None:
            resource = 'This resource' if not resource else f'The rosource {resource}'
            raise ValueError(f'{resource} requires a valid token. Initialize the DataClient '
                             f'object with the `token` argument set.')
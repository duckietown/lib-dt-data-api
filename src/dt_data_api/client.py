from .api import DataAPI
from .storage import Storage


class DataClient(object):

    def __init__(self, token=None):
        self._api = DataAPI(token)

    @property
    def api(self):
        return self._api

    def storage(self, name):
        return Storage(self.api, name)

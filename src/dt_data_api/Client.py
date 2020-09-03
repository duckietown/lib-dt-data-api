from .API import DataAPI
from .Storage import Storage


class DataClient(object):

    def __init__(self, token):
        self._api = DataAPI(token)

    @property
    def api(self):
        return self._api

    def storage(self, name):
        return Storage(self.api, name)

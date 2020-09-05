from .api import DataAPI
from .storage import Storage


class DataClient(object):
    """
    Provides an interface to the Duckietown Cloud Storage Service (DCSS).

    Args:
        token (:obj:`str`): you secret Duckietown Token

    Raises:
        dt_authentication.InvalidToken: The given token is not valid.

    """

    def __init__(self, token: str = None):
        self._api = DataAPI(token)

    @property
    def api(self):
        """
        The low-level Data API client.
        """
        return self._api

    def storage(self, name: str) -> Storage:
        """
        Creates a :py:class:`dt_data_api.Storage` that interfaces to a specific storage
        space among those available on the DCSS.
        """
        return Storage(self.api, name)

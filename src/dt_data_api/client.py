from typing import Union

from .logging import logger
from .api import DataAPI
from .exceptions import ConfigurationError
from .storage import Storage, UserStorage


class DataClient(object):
    """
    Provides an interface to the Duckietown Cloud Storage Service (DCSS).

    Args:
        token (:obj:`str`):         your secret Duckietown Token

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

    def storage(self, name: str, impersonate: Union[None, int] = None) -> Storage:
        """
        Creates a :py:class:`dt_data_api.Storage` that interfaces to a specific storage
        space among those available on the DCSS.

        Args:
            name (:obj:`str`):          Name of the storage space.
            impersonate (:obj:`int`):   (Optional) ID of the user to impersonate. Only valid
                                        when ``name = "user"``.

        """
        name = name.strip()
        # handle special case of `user` storage space
        if name == "user":
            if self._api.uid is None:
                raise ConfigurationError("The 'user' storage space can only be created from an "
                                         "authenticated client. Please, pass a Duckietown token "
                                         "while creating the 'DataClient' object.")
            return UserStorage(self.api, "user", impersonate=impersonate)
        # warn the user when `impersonate` is not used properly
        if impersonate is not None:
            logger.warning("The argument `impersonate` is taken into account only when accessing "
                           "the 'user' storage space. It will be ignored.")
        # any other DCSS storage unit
        return Storage(self.api, name)

from typing import Dict, Optional, Union

from .logging import logger
from .api import DataAPI
from .exceptions import ConfigurationError
from .storage import Storage, UserStorage


class DataClient(object):
    """
    Provides an interface to the Duckietown Cloud Storage Service (DCSS).

    Args:
        token (:obj:`str`):                  your secret Duckietown Token
        public_storage_endpoint (:obj:`str`): (Optional) endpoint for public storage.
        storage_endpoints (:obj:`dict`):     (Optional) endpoints keyed by storage space.

    Raises:
        dt_authentication.InvalidToken: The given token is not valid.

    """

    def __init__(
        self,
        token: str = None,
        public_storage_endpoint: Optional[str] = None,
        storage_endpoints: Optional[Dict[str, str]] = None,
    ):
        self._api = DataAPI(token)
        self._public_storage_endpoint = public_storage_endpoint
        self._storage_endpoints = dict(storage_endpoints or {})
        if public_storage_endpoint is not None:
            configured_endpoint = self._storage_endpoints.get("public")
            if configured_endpoint is not None and configured_endpoint != public_storage_endpoint:
                raise ValueError("Conflicting public storage endpoint configuration.")
            self._storage_endpoints["public"] = public_storage_endpoint

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
                raise ConfigurationError(
                    "The 'user' storage space can only be created from an "
                    "authenticated client. Please, pass a Duckietown token "
                    "while creating the 'DataClient' object."
                )
            return UserStorage(
                self.api,
                "user",
                impersonate=impersonate,
                storage_endpoint=self._storage_endpoints.get(name),
            )
        # warn the user when `impersonate` is not used properly
        if impersonate is not None:
            logger.warning(
                "The argument `impersonate` is taken into account only when accessing "
                "the 'user' storage space. It will be ignored."
            )
        # any other DCSS storage unit
        return Storage(
            self.api,
            name,
            storage_endpoint=self._storage_endpoints.get(name),
        )

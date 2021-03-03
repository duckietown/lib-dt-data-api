import requests

from typing import Dict

from dt_authentication import DuckietownToken
from .constants import DATA_API_URL
from .exceptions import APIError


class DataAPI(object):
    """
    Provides an interface to the RESTful Data API service. The RESTful Data API service
    generates signed URLs that allow you to perform operations on files on the DCSS.

    You should not use this class yourself, the DataClient will do it for you.

    Args:
        token (:obj:`str`): you secret Duckietown Token

    Raises:
        dt_authentication.InvalidToken: The given token is not valid.
    """

    def __init__(self, token: str):
        self._uid = None
        # validate the token
        if token is not None:
            self._uid = DuckietownToken.from_string(token).uid
        # store the raw token
        self._token = token

    @property
    def uid(self) -> int:
        """ The user ID corresponding to the given token """
        return self._uid

    @property
    def token(self) -> str:
        """ The given token """
        return self._token

    def authorize_request(self, action: str, bucket: str, obj: str, headers: Dict[str, str] = None):
        """
        Authorizes the request to perform a given ``action`` on a given object ``obj``
        in the storage space ``bucket``.

        Args:
            action (:obj:`str`):        Action to perform on the object. Allowed values are listed
                                        `here <https://docs.aws.amazon.com/AmazonS3/latest/API/
                                        API_Operations_Amazon_Simple_Storage_Service.html>`_.

            bucket (:obj:`str`):        Name of the target storage space (e.g., ``public``).

            obj (:obj:`str`):           Path to the file to perform the action on.

            headers (:obj:`dict`):      Dictionary containing extra headers that will be sent
                                        together with the action request once the signed URL is
                                        generated.

        Raises:
            dt_data_api.APIError:       An error occurs while communicating with the DCSS.
        """
        api_url = DATA_API_URL.format(action=action, bucket=bucket, object=obj)
        api_headers = {"X-Duckietown-Token": self._token}
        if headers is not None:
            api_headers.update(headers)
        # request authorization
        res = requests.get(api_url, headers=api_headers)
        if res.status_code != 200:
            raise APIError(f"API Error: Code: {res.status_code} Message: {res.text}")
        # parse answer
        answer = res.json()
        if answer["code"] != 200:
            raise APIError(f'API Error: Code: {answer["code"]} Message: {answer["message"]}')
        # get signed url
        return answer["data"]["url"]

import requests

from dt_authentication import DuckietownToken
from .constants import DATA_API_URL
from .exceptions import APIError


class DataAPI(object):

    def __init__(self, token):
        # validate the token
        DuckietownToken.from_string(token)
        # store the raw token
        self._token = token

    def authorize_request(self, action, bucket, obj, headers=None):
        api_url = DATA_API_URL.format(action=action, bucket=bucket, object=obj)
        api_headers = {
            'X-Duckietown-Token': self._token
        }
        if headers is not None:
            api_headers.update(headers)
        # request authorization
        res = requests.get(api_url, headers=api_headers)
        if res.status_code != 200:
            raise APIError(f'API Error: Code: {res.status_code} Message: {res.text}')
        # parse answer
        answer = res.json()
        if answer['code'] != 200:
            raise APIError(f'API Error: Code: {answer["code"]} Message: {answer["message"]}')
        # get signed url
        return answer['data']['url']

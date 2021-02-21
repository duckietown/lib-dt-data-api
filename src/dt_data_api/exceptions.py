class ConfigurationError(BaseException):
    """
    Client configuration error.
    """

    pass


class APIError(BaseException):
    """
    Error while talking to the RESTful Data API endpoints.
    """

    pass


class TransferError(BaseException):
    """
    Error while transferring data to or from a storage space on the DCSS.
    """

    pass


class TransferAborted(BaseException):
    """
    Internal Use Only.
    Used to force `requests` to interrupt a streaming of data to the DCSS.
    """

    pass

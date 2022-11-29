Get Started
===========

The Duckietown Cloud Storage Service (DCSS) is organized in **Storage** spaces,
each one identified by a unique name.
The default storage spaces provided by Duckietown are named **public** and **private**.

The **public** storage space contains data that can be downloaded by anyone on the internet.
Writing to this storage space is not allowed to the public, explicit access must be granted
by an administrator.

The **private** storage space contains data that can be uploaded and downloaded only by those
users who are granted permission to.

Duckietown will make new (sometimes temporary) storage spaces available to the community, these
spaces will be used to collect data relative to time-limited events (e.g., competitions, contests).
All these spaces will become accessible through the same API.


Data Client
-----------

The main interface to the Duckietown Cloud Storage Service (DCSS) is the ``DataClient`` class.
You can create a ``DataClient`` object as follows

.. code-block:: python

    from dt_data_api import DataClient

    client = DataClient()

This is enough for you to be able to access all public resources available on the DCSS.
The Data API library provides the :py:class:`dt_data_api.Storage` class to ease interaction
with specific Storage spaces.

You can create a ``Storage`` object pointing to the **public** storage space as follows

.. code-block:: python

    from dt_data_api import DataClient

    client = DataClient()
    storage = client.storage("public")


Authentication
--------------

An **authenticated client** is a DataClient object initialized with a valid Duckietown Token.
An authenticated client gains automatically access to all the resources the user has permissions
for.

You can create an authenticated client as follows,

.. code-block:: python

    from dt_data_api import DataClient

    client = DataClient("YOUR-TOKEN-HERE")

Where the string ``"YOUR-TOKEN-HERE"`` is replaced with your real Duckietown Token.


Permissions
+++++++++++

Permissions are granted by administrators through the
`Cloud Storage <https://dashboard.duckietown.org/cloud_storage>`_
page on the official Duckietown Dashboard.

Permissions on the DCSS are linked to a user's Duckietown Token. You can get your Duckietown
Token from `this link <https://www.duckietown.org/site/your-token/>`_.


Download an object to file
--------------------------

You can download an object from the DCSS using the following snippet,

.. code-block:: python

    from dt_data_api import DataClient

    client = DataClient()
    storage = client.storage("public")
    storage.download('my_dir/my_file.txt', './my_file.txt')

The code above will download the object with key `my_dir/my_file.txt` stored in the `public`
storage space to the local file `./my_file.txt`.

.. note::
    You can download any file from the `public` storage space using a non-authenticated
    client. Other non-public storage spaces usually require you to have enough permissions
    before you can download any file.
    Check out the section `Authentication`_ to see how to create an authenticated client.


Download an object as bytes
---------------------------

You can download a file from the DCSS in a byte buffer using the following snippet,

.. code-block:: python

    from dt_data_api import DataClient

    client = DataClient()
    storage = client.storage("public")
    download = storage.download('my_dir/my_file.txt')
    download.join()
    data: bytes = download.data

The code above will download the object with key `my_dir/my_file.txt` stored in the `public`
storage space into a byte buffer object.


Upload a file
-------------

You can upload a file to the DCSS using the following snippet,

.. code-block:: python

    from dt_data_api import DataClient

    client = DataClient("YOUR-TOKEN-HERE")
    storage = client.storage("private")
    storage.upload('./my_file.txt', 'my_dir/my_file.txt')

The code above will upload the file `./my_file.txt` to `my_dir/my_file.txt` on the `private`
storage space.


Upload from byte buffer
-----------------------

You can upload the content of a byte buffer to the DCSS using the following snippet,

.. code-block:: python

    from dt_data_api import DataClient

    client = DataClient("YOUR-TOKEN-HERE")
    storage = client.storage("private")
    data = b"my_binary_content"
    storage.upload(data, 'my_dir/my_file.txt')

The code above will upload the bytes in `data` to `my_dir/my_file.txt` on the `private`
storage space.


Monitor the transfer
--------------------

Every time you execute an upload/download action throw the methods
:py:meth:`dt_data_api.Storage.download` and :py:meth:`dt_data_api.Storage.upload`,
an object of type :py:class:`dt_data_api.TransferHandler` is returned right away.
The call is by default non-blocking.
This object lets you monitor and control the transfer.

For example, if you want to print out the progress of your transfer, you
can create a simple callback as follows,

.. code-block:: python

    def cb(handler):
        print(f'{handler.progress.percentage}%')

    transfer = storage.upload('./my_file.txt', 'my_dir/my_file.txt')
    transfer.register_callback(cb)


The callback will be called every time there is an update in the transfer status.
The snippet above will produce the following output,

.. code-block:: bash

    1%
    4%
    8%
    11%
    14%
    17%
    ...


Code API: dt_data_api
=====================

`DataClient`
------------

.. autoclass:: dt_data_api.DataClient
   :members:


`Storage`
---------

.. autoclass:: dt_data_api.Storage
   :members:


`TransferHandler`
-----------------

.. autoclass:: dt_data_api.TransferHandler
   :members:


`TransferStatus`
----------------

.. autoclass:: dt_data_api.TransferStatus
   :members:


`TransferProgress`
------------------

.. autoclass:: dt_data_api.TransferProgress
   :members:


Exceptions
----------

.. autoclass:: dt_data_api.APIError
   :members:

.. autoclass:: dt_data_api.TransferError
   :members:

.. autoclass:: dt_data_api.InvalidToken
   :members:

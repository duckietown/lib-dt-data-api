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


Download a file
---------------

You can download a file from the DCSS using the following snippet,

.. code-block:: python

    from dt_data_api import DataClient

    client = DataClient()
    storage = client.storage("public")
    storage.download('my_dir/my_file.txt', './my_file.txt')

The code above will download the file `my_dir/my_file.txt` stored in the `public`
storage space to the local file `./my_file.txt`.

.. note::
    You can download any file from the `public` storage space using a non-authenticated
    client. Other non-public storage spaces usually require you to have enough permissions
    before you can download any file.
    Check out the section `Authentication`_ to see how to create an authenticated client.


Upload a file
---------------

You can upload a file to the DCSS using the following snippet,

.. code-block:: python

    from dt_data_api import DataClient

    client = DataClient("YOUR-TOKEN-HERE")
    storage = client.storage("private")
    storage.upload('./my_file.txt', 'my_dir/my_file.txt')

The code above will upload the file `./my_file.txt` to `my_dir/my_file.txt` on the `private`
storage space.


Monitor the transfer
--------------------

Every time you execute an upload/download action on an object, an object of type
:py:class:`dt_data_api.TransferHandler` is returned to you.
This object lets you monitor and control the transfer operation.

For example, if you want to print out the progress of your transfer,

.. code-block:: python

    def cb(handler):
        print(f'{handler.progress.percentage}%')

    h = storage.upload('./my_file.txt', 'my_dir/my_file.txt')
    h.register_callback(cb)


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


`TransferProgress`
------------------

.. autoclass:: dt_data_api.TransferProgress
   :members:

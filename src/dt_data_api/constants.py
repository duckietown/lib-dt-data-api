import os

BUCKET_PREFIX = os.environ.get("DT_BUCKET_PREFIX", "")
BUCKET_NAME = f"{BUCKET_PREFIX}duckietown-{{name}}-storage"
PUBLIC_STORAGE_URL = f"https://{BUCKET_PREFIX}duckietown-{{bucket}}-storage.s3.amazonaws.com/{{object}}"
MAXIMUM_ALLOWED_SIZE = 5368709120
TRANSFER_BUF_SIZE_B = 1024 ** 2

DATA_API_HOST = os.environ.get("DT_DATA_API_HOST", "hub.duckietown.com")
DATA_API_VERSION = "v1"
DATA_API_URL = f"https://{DATA_API_HOST}/api/{DATA_API_VERSION}/dcss/authorize/" \
               f"{{action}}/{{bucket}}/{{object}}"

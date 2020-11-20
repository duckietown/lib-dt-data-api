PUBLIC_STORAGE_URL = "https://duckietown-{bucket}-storage.s3.amazonaws.com/{object}"
BUCKET_NAME = "duckietown-{name}-storage"
MAXIMUM_ALLOWED_SIZE = 5368709120
DATA_API_VERSION = "v1"
DATA_API_URL = "https://data.duckietown.org/%s/{action}/{bucket}/{object}" % DATA_API_VERSION
TRANSFER_BUF_SIZE_B = 1024 ** 2

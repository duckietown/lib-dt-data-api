import dataclasses
from datetime import datetime
from typing import Any

LAST_MODIFIED_FORMAT = "%Y-%m-%dT%H:%M:%S.000Z"


@dataclasses.dataclass
class Item:
    """
    Example of raw XML:

        <Key>assets/dts/billboard/content/Ad-Autolab.txt</Key>
        <LastModified>2022-12-13T03:12:27.000Z</LastModified>
        <ETag>"3e497b280f946c19ea1cb984b59b3c23"</ETag>
        <Size>425</Size>
        <StorageClass>STANDARD</StorageClass>

    """
    key: str
    last_modified: datetime
    etag: str
    size: int
    storage_class: str

    @staticmethod
    def parse_obj(obj) -> 'Item':
        d: dict = _object_to_dict(obj)
        return Item(
            key=d["Key"],
            last_modified=datetime.strptime(d["LastModified"], LAST_MODIFIED_FORMAT),
            etag=d["ETag"].strip('"'),
            size=int(d["Size"]),
            storage_class=d["StorageClass"],
        )


def _object_to_dict(obj: Any) -> dict:
    d: dict = {}
    for ch in obj.children:
        d[ch.name] = ch.text
    return d

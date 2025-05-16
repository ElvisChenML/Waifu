from datetime import datetime
import typing


META_TAG_MARK=":"
DATETIME_META="DATETIME:"
class MemoryItem:

    _summary: str
    _tags: typing.List[str]
    _created_time: datetime

    def _init_created_time(self):
        for i in self._tags:
            if i.startswith(DATETIME_META):
                time_tags = i.replace(DATETIME_META, "")
                self._created_time = datetime.strptime(time_tags, "%Y-%m-%d %H:%M:%S")
                return
        # backoff timestamp
        self._created_time = datetime.fromtimestamp(1745069038)

    def _adjust_tags(self):
        self._tags = [i for i in self._tags if i.count(META_TAG_MARK) == 0]

    def __init__(self, summary: str, tags: typing.List[str]):
        self._summary = summary
        self._tags = tags
        self._init_created_time()
        self._adjust_tags()

    def tags(self) -> typing.List[str]:
        return self._tags

    def summary(self) -> str:
        return self._summary

    def time(self)->datetime:
        return self._created_time
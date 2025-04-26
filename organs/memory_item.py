from datetime import datetime
import typing

class MemoryItem:

    def _init_created_time(self):
        for i in self._tags:
            if i.startswith("DATETIME:"):
                time_tags = i.replace("DATETIME: ", "")
                self._created_time = datetime.strptime(time_tags, "%Y-%m-%d %H:%M:%S")
                return
        # backoff timestamp
        self._created_time = datetime.fromtimestamp(1745069038)

    def __init__(self, summary: str, tags: typing.List[str]):
        self._summary = summary
        self._tags = tags
        self._init_created_time()

    def tags(self) -> typing.List[str]:
        return self._tags

    def summary(self) -> str:
        return self._summary

    def time(self)->datetime:
        return self._created_time
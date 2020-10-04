import hashlib
import os
from typing import Dict


class CachedIO:
    cached: Dict[str, str] = dict()

    @staticmethod
    def open_read(file_name):
        file_name = os.path.realpath(file_name)

        if not isinstance(file_name, str):
            raise TypeError(f"want file name is str type, got {type(file_name)}")

        if file_name in CachedIO.cached:
            return CachedIO.cached[file_name]

        CachedIO.cached[file_name] = content = open(file_name, 'rb').read().decode('utf8')
        return content

    @staticmethod
    def open_write(file_name, content, *args, **kwargs):
        file_name = os.path.realpath(file_name)

        if file_name in CachedIO.cached:
            CachedIO.cached[file_name] = content

        open(file_name, *args, **kwargs).write(content)

    @staticmethod
    def open_digest(file_name):
        file_name = os.path.realpath(file_name)

        m = hashlib.md5()
        m.update(CachedIO.open_read(file_name).encode())
        return m.digest().hex()


# only cached in same thread, and still has bug now...
cached_io = CachedIO()

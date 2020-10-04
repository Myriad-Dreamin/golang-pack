import os
import re
from typing import Iterable

from binding_global import current_path


def simplify_path(path):
    return os.path.relpath(path, current_path).replace('\\', '/')


class MiddleSnake(object):

    @staticmethod
    def from_snake(text):
        return text.replace('_', '-')

    @staticmethod
    def to_snake(text):
        return text.replace('-', '_')


class BigCamel(object):

    @staticmethod
    def from_snake(text):
        return ''.join(x.title() for x in text.split('_'))

    _underscorer1 = re.compile(r'(.)([A-Z][a-z]+)')
    _underscorer2 = re.compile('([a-z0-9])([A-Z])')

    @staticmethod
    def to_snake(text):
        return BigCamel._underscorer2.sub(r'\1_\2', BigCamel._underscorer1.sub(r'\1_\2', text)).lower()


class ConvertStyle(object):

    def __init__(self, value_container=None):
        self.value_container = value_container
        self.fr = None
        self.to = None

    def values(self, value_container):
        self.value_container = value_container
        return self

    def from_style(self, fr):
        self.fr = fr
        return self

    def to_style(self, to):
        self.to = to
        return self

    def do_convert(self):
        if isinstance(self.value_container, Iterable):
            return [self.to.from_style(self.fr.to_style(x)) for x in self.value_container]
        else:
            return self.to.from_style(self.fr.to_style(self.value_container))

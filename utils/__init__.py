import os
import re
from typing import Iterable

from binding_global import current_path


def simplify_path(path):
    return os.path.relpath(path, current_path).replace('\\', '/')


class MiddleSnake(object):

    @staticmethod
    def From(text):
        return text.replace('_', '-')

    @staticmethod
    def To(text):
        return text.replace('-', '_')


class BigCamel(object):

    @staticmethod
    def From(text):
        return ''.join(x.title() for x in text.split('_'))

    _underscorer1 = re.compile(r'(.)([A-Z][a-z]+)')
    _underscorer2 = re.compile('([a-z0-9])([A-Z])')

    @staticmethod
    def To(text):
        return BigCamel._underscorer2.sub(r'\1_\2', BigCamel._underscorer1.sub(r'\1_\2', text)).lower()


class ConvertStyle(object):

    def __init__(self, value_container=None):
        self.value_container = value_container
        self.fr = None
        self.to = None

    def Values(self, value_container):
        self.value_container = value_container
        return self

    def From(self, fr):
        self.fr = fr
        return self

    def To(self, to):
        self.to = to
        return self

    def Do(self):
        if isinstance(self.value_container, Iterable):
            return [self.to.From(self.fr.To(x)) for x in self.value_container]
        else:
            return self.to.From(self.fr.To(self.value_container))
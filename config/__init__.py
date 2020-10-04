import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Union, List, Optional

from go_ast import FuncDesc


class Loader(ABC):
    def __init__(self):
        pass

    @abstractmethod
    def handle_function(self, func: FuncDesc):
        return func


@dataclass
class LoaderConfig(object):
    test: Union[re.Pattern, str]
    target: str
    use: Union[Loader, type, str]


@dataclass
class ModuleConfig(object):
    loaders: List[LoaderConfig] = None


@dataclass
class ParseConfig(object):
    force_update: bool = False


@dataclass
class GolangPackConfig(object):
    src: Optional[str]
    output: Optional[str]
    name: Optional[str] = None
    version: Optional[str] = None
    description: Optional[str] = None
    package: Optional[str] = None
    local_toolset: Optional[str] = None
    local_package: Optional[str] = None
    module: Optional[ModuleConfig] = None
    parse: Optional[ParseConfig] = None

    @staticmethod
    def fill_default(config):

        config.parse = config.parse or ParseConfig()

        config.module = module_config = config.module or ModuleConfig()
        module_config.loaders = module_config.loaders or []

        return config

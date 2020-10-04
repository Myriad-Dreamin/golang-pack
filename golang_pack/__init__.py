import os
import re
from pathlib import Path
from typing import List, Union

from binding_global import current_path
from config import GolangPackConfig
from utils.cache_io import cached_io
from go_ast import FuncDesc
from tools import GolangToolsConfig, GolangToolsImpl, AstDumperImpl


class GolangPack(object):
    # global configuration
    dialect_loader_mapping = dict()

    @staticmethod
    def register_loader(dialect_loader, loader_factory):
        GolangPack.dialect_loader_mapping[dialect_loader] = loader_factory

    # constructor

    def __init__(self, config):
        self.config = config  # type: GolangPackConfig
        self.go_tool_config = None  # type: Union[GolangToolsConfig, None]
        self.toolset = None  # type: Union[GolangToolsImpl, None]
        self.go_env = None  # type: Union[dict, None]

        self.process_config()

    # getter

    # configuration process

    def process_config(self):
        self.config = GolangPackConfig.fill_default(self.config)

        self.do_config_golang_tools()

        self.do_config_loaders()
        self.do_config_golang_package()

    def do_config_golang_tools(self):

        force_update = self.config.parse.force_update
        self.go_tool_config = GolangToolsConfig(force_update=force_update)

        self.toolset = GolangToolsImpl(config=self.go_tool_config)

    def do_config_loaders(self):

        for loader in self.config.module.loaders:
            if isinstance(loader.test, str):
                loader.test = re.compile(loader.test)
            if isinstance(loader.use, str):
                loader.use = self.dialect_loader_mapping[loader.use]

            if isinstance(loader.use, type):
                loader.use = loader.use()

    def do_config_golang_package(self):
        using_go_module = self.toolset.is_golang_using_go_module()
        if not using_go_module:
            raise NotImplementedError("you must use go module for golang-pack...")

        go_mod = self.toolset.env.get('GOMOD')
        if go_mod is not None:
            go_mod = os.path.abspath(go_mod)
        if self.config.local_package:
            self.do_config_golang_local_package(go_mod)

    def do_config_golang_local_package(self, go_mod):
        self.config.local_package = os.path.abspath(self.config.local_package)
        self.config.package = self.toolset.read_golang_module_name(self.config.local_package)
        pkg_path = Path(self.config.package)
        self.config.src = str(pkg_path.joinpath(self.config.src)).replace('\\', '/')
        self.config.output = str(pkg_path.joinpath(self.config.output)).replace('\\', '/')

        self.generate_golang_pack_mod(go_mod)

    def generate_golang_pack_mod(self, go_mod):

        # check go.mod file existence
        target_go_mod = os.path.join(current_path, 'go.mod')
        if go_mod and target_go_mod == go_mod and \
                self.toolset.read_golang_module_name(current_path) != 'local-golang-pack-module':
            raise IOError(f"conflict create go.mod, already exists a file at {go_mod} that are not generated")

        # generate go.mod file
        main_version, major, _ = self.toolset.go_version_repr()

        replaces, requires = [], []

        # link local package
        replaces.append(f'{self.config.package} v0.0.0 => {self.config.local_package}')
        requires.append(f'{self.config.package} v0.0.0')

        # check golang-pack tools path option
        golang_pack_version = 'v0.0.0'

        if self.config.local_toolset:
            self.config.local_toolset = os.path.abspath(self.config.local_toolset)
            replaces.append(
                f'github.com/Myriad-Dreamin/golang-pack {golang_pack_version} => {self.config.local_toolset}')
        else:
            golang_pack_version = 'latest'
        requires.append(f'github.com/Myriad-Dreamin/golang-pack {golang_pack_version}')

        replaces, requires = '\n    '.join(replaces), '\n    '.join(requires),

        open(target_go_mod, 'w').write(f"""// GOLANG PACK GENERATED, DO NOT EDIT...
module local-golang-pack-module\n\ngo {main_version}.{major}\n
replace(\n    {replaces}\n)\n
require(\n    {requires}\n)\n
""")

        # ignore generated file
        ignore_file = os.path.join(current_path, '.gitignore')
        ignoring = {'go.mod', 'go.sum'}
        if os.path.exists(ignore_file):
            ignored = set(open(ignore_file, 'r').readlines())
            ignored.update(ignoring)
            ignoring = '\n'.join(sorted(list(ignored)))
        open(ignore_file, 'w+').write(ignoring)

    # run golang pack

    def once(self):

        if self.config.src is not None:
            self.once_package(self.config.src)

    def hot_update(self):
        pass

    def once_package(self, pkg):
        loaders = self.config.module.loaders
        if loaders is None:
            return

        ast_info = AstDumperImpl(config=self.go_tool_config, toolset=self.toolset).dump_ast(pkg)

        file_function_mapping = dict()

        for desc in ast_info.functions.items:
            file_function_mapping[desc.pos.file] = desc_list = file_function_mapping.get(desc.pos.file, [])
            desc_list.append(desc)

        for k, funcs in file_function_mapping.items():
            for loader in loaders:
                if loader.test.match(k):
                    self.invoke_loader(loader, k, funcs)
                    break

    # inner methods

    def invoke_loader(self, loader, file, funcs: List[FuncDesc]):
        _ = self
        target_file = self.eval_file(file, loader.target)
        offsets = []

        for func in funcs:
            offsets.append((func.pos.offset, func))
        offsets.sort(key=lambda t: t[0])

        source = cached_io.open_read(file)
        source_pieces = []
        last_index = 0
        for offset, func in offsets:
            source_pieces.append(source[last_index:offset])
            last_index = func.pos.length + func.pos.offset
            stmts = loader.use.handle_function(func)
            source_pieces.append('\n'.join(map(str, stmts)))
        source_pieces.append(source[last_index:])
        dir_name = os.path.dirname(target_file)
        os.makedirs(dir_name, exist_ok=True)
        cached_io.open_write(target_file, ''.join(source_pieces), 'w')
        self.toolset.go_fmt([target_file])

    def eval_file(self, file, target):

        # break target file path
        target_pieces = filter(lambda s: len(s) > 0, re.split(r'((?:\[[^]]*])|@)', target))
        compiled_target_pieces = []

        # break target file path
        for target_piece in target_pieces:
            if target_piece == '@':
                if len(compiled_target_pieces) != 0:
                    raise AssertionError("@ must be at first")
                target_piece = current_path
            elif len(target_piece) > 1 and target_piece[0] == '[':
                target_piece = target_piece[1:-1]
                if target_piece == "file-name":
                    target_piece = os.path.basename(file)
                    target_piece, _ = target_piece.split('.', maxsplit=1)
                elif target_piece.startswith('hash:'):
                    target_piece = cached_io.open_digest(file)[:int(target_piece[5:])]
            compiled_target_pieces.append(target_piece)
        target = ''.join(compiled_target_pieces)

        # determine the start path of (maybe relative) target file path
        assert len(target) > 0
        if target[0].isalnum():
            target_dir = os.path.abspath(os.path.dirname(file))
            if self.config.output is not None:
                rel_pkg = os.path.relpath(self.config.src, self.config.package)
                maybe_root = target_dir[:len(target_dir) - len(rel_pkg)]
                target_dir = os.path.join(maybe_root, os.path.relpath(self.config.output, self.config.package))
            target = os.path.join(target_dir, target)

        return os.path.realpath(target)

from typing import List

import go_ast.decorator
from .decorator import use_file_mapping

from utils.cache_io import cached_io
from utils import simplify_path


class Object(object):
    def __init__(self, doc_tree=None):
        if doc_tree:
            self.name = doc_tree['n']
            self.type = doc_tree['t']
        else:
            self.name = self.type = ''

    def __repr__(self):
        return f'{self.name}(T:{self.type})'

    @staticmethod
    def create(name, t):
        x = Object()
        x.name = name
        x.type = t
        return x


class FilePos(object):
    def __init__(self, doc_tree):
        self.file = doc_tree['f']
        self.line = doc_tree['l']
        self.column = doc_tree['c']
        self.offset = doc_tree['o']
        self.length = doc_tree['s']

    def __repr__(self):
        return ':'.join(map(str, [self.file, self.line, self.column]))

    def use_file_mapping(self, mp):
        self.file = mp[self.file]


class WithFilePos(object):
    def __init__(self, doc_tree):
        if doc_tree:
            self.pos = FilePos(doc_tree['p'])
        else:
            self.pos = None

    @property
    def body_content(self):
        if self.pos is None:
            raise KeyError("in memory stmt has no file position")
        f = cached_io.open_read(self.pos.file)
        return f[self.pos.offset:self.pos.offset + self.pos.length]

    def __str__(self):
        return self.body_content

    def __repr__(self):
        content = self.body_content
        if len(content) > 30:
            content = content[:30] + '...'
        if self.pos:
            pos = ':'.join(map(str, [self.pos.line, self.pos.column, self.pos.length]))
        else:
            pos = ':memory:'
        return f"<{self.__class__.__name__} at {pos}, body='{content}'> "


class FilesMapping(object):
    def __init__(self, doc_tree):
        self.mapping = doc_tree

    def __getitem__(self, k):
        return simplify_path(self.mapping[k])


@use_file_mapping('items')
class ImportStmts(object):
    @use_file_mapping
    class Item(object):
        def __init__(self, doc_tree):
            self.pos = FilePos(doc_tree['p'])
            self.alias = doc_tree['alias']
            self.path = doc_tree['path']

        def __repr__(self):
            if self.alias is not None and len(self.alias):
                return f'<{self.alias} from {self.path} at {repr(self.pos)}>'
            return f'<{self.path} at {repr(self.pos)}>'

    def __init__(self, doc_tree):
        self.items = list(map(ImportStmts.Item, doc_tree))

    def __repr__(self):
        items = self.items
        if len(items) > 20:
            return '\n'.join(map(repr, items[:5])) + '\n...'
        return '\n'.join(map(repr, items))


class Stmt(WithFilePos):
    polymorphic = dict()

    @staticmethod
    def create_stmt(doc_tree):
        if doc_tree['t'] not in Stmt.polymorphic:
            raise KeyError(f"stmt type {doc_tree['t']} not registered")

        return Stmt.polymorphic[doc_tree['t']](doc_tree)


@use_file_mapping
class BinaryExp(Stmt):
    def __init__(self, doc_tree):
        super().__init__(doc_tree)


@use_file_mapping
class UnaryExp(Stmt):
    def __init__(self, doc_tree):
        super().__init__(doc_tree)


@use_file_mapping('callee', 'ins')
class CallExp(Stmt):
    def __init__(self, doc_tree):
        super().__init__(doc_tree)
        self.callee = Stmt.create_stmt(doc_tree['c'])  # type: Stmt
        self.variadic = doc_tree['v']
        self.ins = list(map(Stmt.create_stmt, doc_tree['i']))  # type: List[Stmt]


@use_file_mapping
class OpaqueExp(Stmt):
    def __init__(self, doc_tree):
        super().__init__(doc_tree)
        self.opaque = "" if doc_tree is None else doc_tree["o"]

    @staticmethod
    def create(opaque):
        o = OpaqueExp(None)
        o.opaque = opaque
        return o

    def __str__(self):
        return self.opaque


@use_file_mapping('lhs', 'rhs')
class AssignExp(Stmt):
    def __init__(self, doc_tree):
        super().__init__(doc_tree)
        self.lhs = list(map(Stmt.create_stmt, doc_tree['l']))  # type: List[Stmt]
        self.rhs = list(map(Stmt.create_stmt, doc_tree['r']))  # type: List[Stmt]

    def __str__(self):
        return (','.join(map(str, self.lhs))) + " := " + (','.join(map(str, self.rhs)))


@use_file_mapping('items')
class BlockExp(Stmt):

    def __init__(self, doc_tree):
        super().__init__(doc_tree)
        self.items = list(map(Stmt.create_stmt, doc_tree['b']))  # type: List[Stmt]

    def __str__(self):
        return '\n'.join(map(str, self.items))


@use_file_mapping
class SelectExp(BlockExp):
    def __init__(self, doc_tree):
        super().__init__(doc_tree)


@use_file_mapping
class IfExp(Stmt):
    def __init__(self, doc_tree):
        super().__init__(doc_tree)


@use_file_mapping
class IdentExp(Stmt):
    def __init__(self, doc_tree):
        super().__init__(doc_tree)
        self.ident = Object(doc_tree['o'])


@use_file_mapping('decls')
class VarDeclExp(Stmt):
    def __init__(self, doc_tree):
        super().__init__(doc_tree)
        self.decls = list(map(Stmt.create_stmt, doc_tree['s']))  # type: List[VarSpecExp]


@use_file_mapping('values', 'type_spec')
class VarSpecExp(Stmt):
    def __init__(self, doc_tree):
        super().__init__(doc_tree)
        self.names = doc_tree['l']
        if 'r' in doc_tree:
            self.values = list(map(Stmt.create_stmt, doc_tree['r']))  # type: List[Stmt]
        else:
            self.values = []
        if doc_tree.get('ts'):
            self.type_spec = Stmt.create_stmt(doc_tree['ts'])
        else:
            self.type_spec = None


@use_file_mapping('type_spec')
class TypeSpecExp(Stmt):
    def __init__(self, doc_tree):
        super().__init__(doc_tree)
        self.names = doc_tree['n']
        if doc_tree.get('ts'):
            self.type_spec = Stmt.create_stmt(doc_tree['ts'])
        else:
            self.type_spec = None


@use_file_mapping('x')
class SelectorExp(Stmt):
    def __init__(self, doc_tree):
        super().__init__(doc_tree)
        self.x = Stmt.create_stmt(doc_tree['x'])  # type: Stmt
        self.name = doc_tree['n']


Stmt.polymorphic = {
    'b': BinaryExp,
    'u': UnaryExp,
    'c': CallExp,
    'o': OpaqueExp,
    'a': AssignExp,
    'k': BlockExp,
    's': SelectExp,
    'i': IfExp,
    'var': VarDeclExp,
    'id': IdentExp,
    'v': VarSpecExp,
    't': TypeSpecExp,
    'l': SelectorExp,
}


@use_file_mapping('items')
class FuncBody(BlockExp):
    def __init__(self, doc_tree):
        super().__init__(doc_tree)


@use_file_mapping('body')
class FuncDesc(WithFilePos):
    def __init__(self, doc_tree):
        super().__init__(doc_tree)
        self.recv = Object(doc_tree['r'])
        self.name = doc_tree['n']
        self.ins = list(map(Object, doc_tree['in']))
        self.outs = list(map(Object, doc_tree['out']))
        self.body = FuncBody(doc_tree['body'])

    def __repr__(self):
        return f"<{self.recv.type}.{self.name} at {repr(self.pos)}, body={repr(self.body)}>"

    def __str__(self):
        ins = ", ".join(
            map(lambda obj: f"{obj.name} {obj.type}", self.ins))
        outs = map(lambda obj: f"{obj.name} {obj.type}", self.outs)
        if len(self.outs) == 0:
            outs = ""
        elif len(self.outs) == 1 and len(self.outs[0].name) == 0:
            outs = next(outs)
        else:
            outs = f"({', '.join(outs)})"
        return f'func ({self.recv.name} {self.recv.type}) {self.name}({ins}) {outs} {{\n{str(self.body)}\n}}'


@use_file_mapping('items')
class FuncDescs(object):

    def __init__(self, doc_tree):
        self.items = list(map(FuncDesc, doc_tree))

    def __repr__(self):
        items = self.items
        if len(items) > 20:
            return '\n'.join(map(repr, items[:5])) + '\n...'
        return '\n'.join(map(repr, items))


def use_file_mapping_not_report_error(target, mp):
    target.use_file_mapping(mp)


class ASTInfo(object):
    def __init__(self, doc_tree):
        self.file_mapping = FilesMapping(doc_tree['file_mapping'])
        self.imports = ImportStmts(doc_tree['imports'])
        self.functions = FuncDescs(doc_tree['functions'])
        # noinspection PyTypeChecker
        use_file_mapping_not_report_error(self.imports, self.file_mapping)
        # noinspection PyTypeChecker
        use_file_mapping_not_report_error(self.functions, self.file_mapping)

    def __repr__(self):
        return f"""imports:\n{repr(self.imports)}\nfunctions:\n{repr(self.functions)}"""

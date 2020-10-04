from collections import deque
from dataclasses import dataclass
from typing import List

from config import Loader
from go_ast import FuncDesc, AssignExp, VarDeclExp, CallExp, OpaqueExp, Stmt, SelectorExp, Object


class StubLoader(Loader):
    @dataclass
    class Context(object):
        fn: FuncDesc
        context_vars: set
        local_vars: dict
        created_context: bool = False
        created_ok: bool = False
        created_err: bool = False

    def __init__(self):
        super().__init__()

        self.fn_sub_handlers = {
            AssignExp: self.check_assign_exp,
            VarDeclExp: self.check_var_decl_exp,
            CallExp: self.check_call_exp,
        }  # type: Dict[type, lambda _:[_]]

        invoking_stub_handlers = {
            'Context': self.invoking_stub_context,
            'Serve': self.invoking_stub_serve,
            'ServeKeyed': self.invoking_stub_serve_keyed,
        }

        stub_handlers = {
            'GetID': self.stub_get_id,
            'GetIDKeyed': self.stub_get_id_keyed,
            'AbortIf': self.stub_abort_if,
            'Bind': self.stub_bind,
            'Next': self.stub_next,
            'Emit': self.stub_emit,
            'EmitSelf': self.stub_emit_self,
        }

        stub_handlers.update(invoking_stub_handlers)

        promise_handlers = {
            'Then': self.promise_then,
            'Catch': self.promise_catch,
            'Finally': self.promise_finally,
            'ThenDo': self.promise_then_do,
            'CatchDo': self.promise_catch_do,
        }

        self.callee_fn_handlers = {
            'Binder': stub_handlers,
            'Stub': stub_handlers,
            'InvokingStub': invoking_stub_handlers,
            'Promise': promise_handlers,
        }  # type: Dict[str, Dict[str, lambda _:[_]]]

    def handle_function(self, func: FuncDesc):
        _ = self
        if func.name != "PostSubmission":
            return [func]

        items = []
        context = StubLoader.Context(fn=func, context_vars=set(), local_vars=dict())

        for item in func.body.items:
            t = type(item)
            if t in self.fn_sub_handlers:
                items += self.fn_sub_handlers[t](context, item)
            else:
                items.append(item)
        func.body.items = items
        res = []
        if context.created_context:
            fields = []
            for k in context.context_vars:
                fields.append(f'{k.name} {k.type}')
            fields = '\n'.join(fields)
            res.append(OpaqueExp.create(f"""type {func.name}Context struct {{\n{fields}\n}}"""))
        res.append(func)
        return res

    def check_assign_exp(self, context: Context, a: AssignExp):
        if len(a.rhs) != 1:
            return [a]
        rhs = a.rhs[0]
        if not isinstance(rhs, CallExp):
            return [a]

        return self.handle_stub_call(context, a.lhs, rhs, a)

    def check_call_exp(self, context: Context, a: CallExp):
        return self.handle_stub_call(context, [], a, a)

    def handle_stub_call(self, context: Context, lhs: List[Stmt], a: CallExp, raw):
        # callee = a.callee.body_content
        # if callee.startswith(context.fn.recv.name):
        #     callee = callee[len(context.fn.recv.name) + 1:].split('(', maxsplit=1)[0]
        #     if callee in self.callee_fn_handlers:
        #         return self.callee_fn_handlers[callee](context, lhs, a)

        q = deque()
        callee = a
        while callee:
            if isinstance(callee, SelectorExp):
                q.append(tuple([callee.name]))
                callee = callee.x
            elif isinstance(callee, CallExp):
                assert isinstance(callee.callee, SelectorExp)
                q.append((callee.callee.name, callee.ins))
                callee = callee.callee.x
            else:
                callee = None

        start_stub, current_type = False, None

        res = []
        while len(q):
            p = q.pop()
            if len(p) == 1:
                # todo: search type
                current_type = p[0]
            elif len(p) == 2:
                if current_type is None:
                    raise AssertionError("unknown type of invoker")
                if current_type not in self.callee_fn_handlers:
                    if not start_stub:
                        return [raw]
                    raise AssertionError(f"maybe a bug, want type dict {current_type}")
                start_stub = True
                handlers = self.callee_fn_handlers[current_type]
                current_type, res_sub = handlers[p[0]](context, [] if len(q) else lhs, p[1])
                res.extend(res_sub)
            else:
                raise AssertionError(f"maybe a bug, got {p}")

        return res

    def check_var_decl_exp(self, context: Context, a: VarDeclExp):
        _ = self
        if len(a.decls) != 1:
            return [a]

        for decl in a.decls:
            # detect new
            if decl.values and len(decl.values) == 1:
                rhs = decl.values[0]
                if not isinstance(rhs, CallExp):
                    return [a]
                if rhs.callee.body_content != "new":
                    return [a]
                t = rhs.ins[0].body_content
                for name in decl.names:
                    context.local_vars[name] = Object.create(name, "*" + t)

            # detect null declare
            if decl.type_spec:
                t = decl.type_spec
                for name in decl.names:
                    context.local_vars[name] = Object.create(name, t)

        return [a]

    # noinspection PyUnresolvedReferences
    def stub_get_id(self, context: Context, lhs: List[Stmt], rhs: List[Stmt]):
        assert len(rhs) == 0
        assert len(lhs) == 1

        idName = lhs[0].ident.name.title()

        res = self.must_create_context(context, [])
        res = self.must_create_ok_decl(context, res)
        context.context_vars.add(Object.create(idName, 'uint'))

        res.append(OpaqueExp.create(f"context.{idName}, ok = snippet.ParseUint(c, {context.fn.recv.name}.key)"))
        res.append(OpaqueExp.create("if !ok {\nreturn\n}"))
        return None, res

    # noinspection PyUnresolvedReferences
    def stub_get_id_keyed(self, context: Context, lhs: List[Stmt], rhs: List[Stmt]):
        _ = self
        res = []

        return None, res

    # noinspection PyUnresolvedReferences
    def stub_abort_if(self, context: Context, lhs: List[Stmt], rhs: List[Stmt]):
        _ = self
        res = []

        return None, res

    # noinspection PyUnresolvedReferences
    def stub_next(self, context: Context, lhs: List[Stmt], rhs: List[Stmt]):
        _ = self
        res = []

        return None, res

    # noinspection PyUnresolvedReferences
    def stub_bind(self, context: Context, lhs: List[Stmt], rhs: List[Stmt]):
        assert len(lhs) == 0

        res = []
        for binding in rhs:
            bc = binding.body_content
            bc.strip('&').strip()
            if bc not in context.local_vars:
                raise KeyError(f'can not bind {repr(binding)}')
            res = self.must_create_context(context, res)
            local_var = context.local_vars[bc]
            cc = bc.title()
            context.context_vars.add(Object.create(cc, local_var.type))
            res.append(OpaqueExp.create(f"context.{cc} = {bc}"))
            res.append(OpaqueExp.create(f"if !snippet.BindRequest(c, {bc}) {{\nreturn\n}}"))
        return None, res

    def invoking_stub_context(self, context: Context, lhs: List[Stmt], rhs: List[Stmt]):
        _ = self
        res = []

        return 'InvokingStub', res

    def invoking_stub_serve(self, context: Context, lhs: List[Stmt], rhs: List[Stmt]):
        _ = self
        res = []

        return 'Promise', res

    def invoking_stub_serve_keyed(self, context: Context, lhs: List[Stmt], rhs: List[Stmt]):
        _ = self
        res = []

        return 'Promise', res

    def stub_emit_self(self, context: Context, lhs: List[Stmt], rhs: List[Stmt]):
        _ = self
        assert len(lhs) == 0
        res = []
        return 'Promise', res

    def stub_emit(self, context: Context, lhs: List[Stmt], rhs: List[Stmt]):
        _ = self
        assert len(lhs) == 0
        res = []
        return 'Promise', res

    def promise_then(self, context: Context, lhs: List[Stmt], rhs: List[Stmt]):
        _ = self
        assert len(lhs) == 0
        res = []
        return 'Promise', res

    def promise_catch(self, context: Context, lhs: List[Stmt], rhs: List[Stmt]):
        _ = self
        assert len(lhs) == 0
        res = []
        return 'Promise', res

    def promise_finally(self, context: Context, lhs: List[Stmt], rhs: List[Stmt]):
        _ = self
        assert len(lhs) == 0
        res = []
        return 'Promise', res

    def promise_then_do(self, context: Context, lhs: List[Stmt], rhs: List[Stmt]):
        _ = self
        assert len(lhs) == 0
        res = []
        return 'Promise', res

    def promise_catch_do(self, context: Context, lhs: List[Stmt], rhs: List[Stmt]):
        _ = self
        assert len(lhs) == 0
        res = []
        return 'Promise', res

    def must_create_context(self, context: Context, res):
        _ = self
        if not context.created_context:
            context.created_context = True
            res.append(
                OpaqueExp.create(f"var context {context.fn.name}Context")
            )
        return res

    def must_create_ok_decl(self, context: Context, res):
        _ = self
        if not context.created_ok:
            context.created_ok = True
            res.append(OpaqueExp.create(f"var ok bool"))
        return res

    def must_create_err_decl(self, context: Context, res):
        _ = self
        if not context.created_err:
            context.created_err = True
            res.append(OpaqueExp.create(f"var err error"))
        return res
from collections import deque
from dataclasses import dataclass
from typing import List, Dict, Optional

from config import Loader
from go_ast import FuncDesc, AssignExp, VarDeclExp, CallExp, OpaqueExp, Stmt, SelectorExp, Object, IdentExp


@dataclass
class Context(object):
    fn: FuncDesc
    context_vars: dict
    local_vars: dict
    service_methods: dict
    insert_points: dict
    stmt_index: int = 0
    created_context: bool = False
    created_ok: bool = False
    created_err: bool = False


def escape(s):
    return s.replace('"', '\\"')


class StubLoader(Loader):

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
        }  # type: Dict[str, lambda _:[_]]

        stub_handlers = {
            'GetID': self.stub_get_id,
            'GetIDKeyed': self.stub_get_id_keyed,
            'AbortIf': self.stub_abort_if,
            'AbortIfHint': self.stub_abort_if_hint,
            'Bind': self.stub_bind,
        }  # type: Dict[str, lambda _:[_]]

        stub_handlers.update(invoking_stub_handlers)

        promise_handlers = {
            'Then': self.promise_then,
            'Catch': self.promise_catch,
            'Finally': self.promise_finally,
            'ThenRef': self.promise_then_ref,
            'CatchRef': self.promise_catch_ref,
            'FinallyRef': self.promise_finally_ref,
        }  # type: Dict[str, lambda _:[_]]

        self.callee_fn_handlers = {
            'Binder': stub_handlers,
            'Stub': stub_handlers,
            'InvokingStub': invoking_stub_handlers,
            'Promise': promise_handlers,
        }  # type: Dict[str, Dict[str, lambda _:[_]]]

    def handle_function(self, func: FuncDesc):
        items = []
        context = Context(
            fn=func,
            context_vars=dict(), local_vars=dict(),
            service_methods=dict(), insert_points=dict())
        for i, item in enumerate(func.body.items):
            context.stmt_index = i
            new_items = []
            self.handle_stmt(item, context, new_items)
            for x_item in new_items:
                if isinstance(x_item, OpaqueExp):
                    for k, v in context.insert_points.items():
                        x_item.opaque = x_item.opaque.replace(k, '\n'.join(map(str, v)))
            context.insert_points.clear()
            items.extend(new_items)

        func.body.items = items
        res = []
        if context.created_context:
            fields = []
            for k in context.context_vars.values():
                fields.append(f'{k.name} {k.type}')
            fields = '\n'.join(fields)
            res.append(OpaqueExp.create(f"""type {func.name}Context struct {{\n{fields}\n}}"""))

        interface_sub_services = []
        for service_name, value in context.service_methods.items():
            _, _, key = value
            method_name = self.resolve_service_method_handler(context, service_name + 'Service', context.fn.name, key)
            service_name = f"{func.name}{key or 'Self'}Service"
            res.append(OpaqueExp.create(f"""\ntype {service_name} interface {{
{method_name}(context *{func.name}Context) (err error)\n}}"""))
            interface_sub_services.append(service_name)

        interface_sub_services = '\n'.join(interface_sub_services)
        res.append(OpaqueExp.create(f"""\ntype {func.name}Service interface {{\n{interface_sub_services}\n}}"""))

        res.append(func)
        return res

    def handle_stmt(self, item, context, items):
        t = type(item)
        if t in self.fn_sub_handlers:
            items += self.fn_sub_handlers[t](context, item)
        else:
            items.append(item)
        return

    def check_assign_exp(self, context: Context, a: AssignExp):
        if len(a.rhs) != 1:
            return [a]
        rhs = a.rhs[0]
        if not isinstance(rhs, CallExp):
            return [a]

        return self.handle_stub_call(context, a.lhs, rhs, a)

    def check_call_exp(self, context: Context, a: CallExp):
        return self.handle_stub_call(context, [], a, a)

    def resolve_service_method_handler(self, _: Context, _service, method, key: Optional[str]):
        _ = self
        return key or method

    def resolve_service_handler(self, context: Context, service, method, key: Optional[str]):
        method = self.resolve_service_method_handler(context, service, method, key)
        return f'{context.fn.recv.name}.resolver.Require(' \
               f'{context.fn.recv.name}.serviceName).({service}).{method}'

    def handle_stub_call(self, context: Context, lhs: List[Stmt], a: CallExp, raw):
        q = deque()
        callee = a
        while callee:
            if isinstance(callee, SelectorExp):
                q.append(tuple([callee.name]))
                callee = callee.x
            elif isinstance(callee, CallExp):
                if not isinstance(callee.callee, SelectorExp):
                    return [raw]
                q.append((callee.callee.name, callee.ins))
                callee = callee.callee.x
            elif isinstance(callee, IdentExp):
                if callee.body_content != context.fn.recv.name:
                    return [raw]
                callee = None
            else:
                raise TypeError(f'unknown callee ast, content: {callee.body_content} type: {type(callee)}')

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
    def stub_do_get_id(self, context: Context, lhs: List[Stmt], k: str):
        id_name = lhs[0].ident.name.title()

        res = self.must_create_context(context, [])
        res = self.must_create_ok_decl(context, res)
        context.context_vars[id_name] = Object.create(id_name, 'uint')

        res.append(OpaqueExp.create(f"context.{id_name}, ok = snippet.ParseUint(c, {k})"))
        res.append(OpaqueExp.create("if !ok {\nreturn\n}"))

        return None, res

    # noinspection PyUnresolvedReferences
    def stub_get_id(self, context: Context, lhs: List[Stmt], rhs: List[Stmt]):
        assert len(rhs) == 0
        assert len(lhs) == 1
        return self.stub_do_get_id(context, lhs, f'{context.fn.recv.name}.key')

    # noinspection PyUnresolvedReferences
    def stub_get_id_keyed(self, context: Context, lhs: List[Stmt], rhs: List[Stmt]):
        assert len(rhs) == 1
        assert len(lhs) == 1
        return self.stub_do_get_id(context, lhs, rhs[0].body_content)

    # noinspection PyUnresolvedReferences
    def stub_do_abort_if_hint(self, context: Context, lhs: List[Stmt], assertion: Stmt, rhs: List[Stmt], hint: str):
        assert len(lhs) == 0
        _ = self

        rest_args = ','.join(map(str, rhs))
        assertion = assertion.body_content
        return None, [
            OpaqueExp.create(
                f"""if {assertion} {{
snippet.DoReportHintRaw(c, "Assertion Failed: want {escape(assertion)}", {hint}, {rest_args})\nreturn\n}}""")]

    # noinspection PyUnresolvedReferences
    def stub_abort_if(self, context: Context, lhs: List[Stmt], rhs: List[Stmt]):
        assert len(rhs) > 0
        return self.stub_do_abort_if_hint(context, lhs, rhs[0], rhs[1:], '0xbad')

    # noinspection PyUnresolvedReferences
    def stub_abort_if_hint(self, context: Context, lhs: List[Stmt], rhs: List[Stmt]):
        assert len(rhs) > 1
        return self.stub_do_abort_if_hint(context, lhs, rhs[0], rhs[2:], rhs[1].body_content)

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
            context.context_vars[cc] = Object.create(cc, local_var.type)
            res.append(OpaqueExp.create(f"context.{cc} = {bc}"))
            res.append(OpaqueExp.create(f"if !snippet.BindRequest(c, {bc}) {{\nreturn\n}}"))
        return None, res

    def invoking_stub_context(self, context: Context, _: List[Stmt], rhs: List[Stmt]):
        _ = self
        res = []

        for binding in rhs:
            bc = binding.body_content
            if bc not in context.local_vars:
                raise KeyError(f'can not serve {repr(binding)}')
            res = self.must_create_context(context, res)
            local_var = context.local_vars[bc]
            tbc = bc.title()
            context.context_vars[tbc] = Object.create(tbc, local_var.type)
            res.append(OpaqueExp.create(f"context.{tbc} = {bc}"))

        return 'InvokingStub', res

    def invoking_stub_do_serve(self, context: Context, _: List[Stmt], rhs: List[Stmt], key: Optional[str]):
        res = []
        res = self.must_create_err_decl(context, res)
        res = self.must_create_context(context, res)

        last_one = rhs[-1]

        service_name = context.fn.name + (key or 'Self')
        serve_handler = self.resolve_service_handler(context, service_name + 'Service', context.fn.name, key)

        if service_name not in context.service_methods:
            context.service_methods[service_name] = method_desc = (list(), list(), key)

            for binding in rhs:
                bc = binding.body_content
                tbc = bc.title()
                if tbc in context.context_vars:
                    method_desc[0].append(context.context_vars[tbc])
                    continue

                if bc in context.local_vars:
                    local_var = context.local_vars[bc]
                    method_desc[0].append(local_var)
                    context.context_vars[tbc] = Object.create(tbc, local_var.type)
                    if binding != last_one:
                        res.append(OpaqueExp.create(f"context.{tbc} = {bc}"))
                    continue
                raise KeyError(f'can not bind {repr(binding)} to service method')

            method_desc[1].append(Object.create('err', 'error'))
        else:
            raise NotImplementedError("todo check signature")
            # method_desc = context.service_methods[service_name]
            #
            # if len(method_desc[0]) != len(rhs):
            #     raise TypeError(f"signature not consistent want {method_desc[0]} got {rhs}")
            #
            # for i, binding in enumerate(rhs):
            #     bc = binding.body_content
            #     tbc = bc.title()
            #
            #     if tbc in context.context_vars:
            #         method_desc[0][i].append(context.context_vars[tbc])
            #
            #     if bc in context.local_vars:
            #         method_desc[0][i].append(context.local_vars[bc])
            #     raise KeyError(f'can not bind {repr(binding)} to service method')
            #
            # method_desc[1].append(Object.create('err', 'error'))
        if_stmt = [
            f"if err = {serve_handler}(&context, ); err != nil {{"
            f'{self.create_promise_handler(context, "catch")}\n'
            f'{self.create_promise_handler(context, "finally")}\nsnippet.DoReport(c, err)\nreturn\n}} else {{']

        for binding in rhs:
            bc = binding.body_content
            tbc = bc.title()
            if bc in context.local_vars:
                if_stmt.append(f"{bc} = context.{tbc}")

        if_stmt.append(f'{self.create_promise_handler(context, "then")}\n'
                       f'{self.create_promise_handler(context, "finally")}}}')

        res.append(OpaqueExp.create('\n'.join(if_stmt)))

        return 'Promise', res

    def invoking_stub_serve(self, context: Context, lhs: List[Stmt], rhs: List[Stmt]):
        assert len(rhs) > 0
        return self.invoking_stub_do_serve(context, lhs, rhs, None)

    def invoking_stub_serve_keyed(self, context: Context, lhs: List[Stmt], rhs: List[Stmt]):
        assert len(rhs) > 1
        # todo: key type
        return self.invoking_stub_do_serve(context, lhs, rhs[1:], rhs[0].body_content[1:-1])

    def promise_insert_stmts(self, context: Context, _: List[Stmt], rhs: List[Stmt], point_name):
        _ = self
        assert len(rhs) == 1
        res = []

        # todo rhs type
        rhs = rhs[0].body_content

        _, rhs = rhs.split('{', maxsplit=1)
        rhs = rhs.strip()[:-1]

        self.get_promise_handler(context, point_name).append(OpaqueExp.create(rhs))
        return 'Promise', res

    def promise_then(self, context: Context, lhs: List[Stmt], rhs: List[Stmt]):
        return self.promise_insert_stmts(context, lhs, rhs, 'then')

    def promise_then_ref(self, context: Context, lhs: List[Stmt], rhs: List[Stmt]):
        return self.promise_then(context, lhs, rhs)

    def promise_catch(self, context: Context, lhs: List[Stmt], rhs: List[Stmt]):
        return self.promise_insert_stmts(context, lhs, rhs, 'catch')

    def promise_catch_ref(self, context: Context, lhs: List[Stmt], rhs: List[Stmt]):
        return self.promise_catch(context, lhs, rhs)

    def promise_finally(self, context: Context, lhs: List[Stmt], rhs: List[Stmt]):
        return self.promise_insert_stmts(context, lhs, rhs, 'finally')

    def promise_finally_ref(self, context: Context, lhs: List[Stmt], rhs: List[Stmt]):
        return self.promise_finally(context, lhs, rhs)

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

    # noinspection PyMethodMayBeStatic
    def create_promise_handler(self, context, handler_type):
        insert_point = f'_ = "serve_promise_{handler_type}_handler{context.stmt_index}"'
        context.insert_points[insert_point] = []
        return insert_point

    # noinspection PyMethodMayBeStatic
    def get_promise_handler(self, context, handler_type):
        return context.insert_points.get(f'_ = "serve_promise_{handler_type}_handler{context.stmt_index}"', [])

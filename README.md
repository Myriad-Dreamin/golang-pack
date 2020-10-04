

# Golang-Pack

## Example

```python
import re
from config import LoaderConfig, ModuleConfig, ParseConfig, GolangPackConfig
from golang_pack import GolangPack
from loader.stub import StubLoader

if __name__ == '__main__':
    # register a loader that can process golang code
    GolangPack.register_loader('stub-loader', StubLoader)

    # module.exports = ...
    golang_pack = GolangPack(GolangPackConfig(
        name='boj-v6',
        version='v0.5.0',
        description='golang pack test config',
        local_toolset='..',
        local_package='F:/work/boj-v6',
        src='cmd/generate/model',
        output='app/generated_controller',
        module=ModuleConfig(
            loaders=[
                LoaderConfig(test=re.compile(r'.*?.stub.go$'), target='[file-name].gen.go', use='stub-loader'),
            ]
        ),
        parse=ParseConfig(
            force_update=True,
        ),
    ))

    # run golang-pack
    golang_pack.once()
```

## Configuration

see file [Golang Config Definitions](https://github.com/Myriad-Dreamin/golang-pack/blob/main/config/__init__.py)

GolangPackConfig:

+ package `str`: the project root that we can visit by go module, it must not be a file path. e.g. :

    + `github/Myriad-Dreamin/golang-pack`

+ local_package `str`: the file path to the project root. if it is defined, package value will not be used e.g. :

    + `github/Myriad-Dreamin/golang-pack`

+ src `str`: a package path that we can visit by go module. it is relative to `package`. e.g. :

    + `cmd/generate/model-definitions`. if `package` is `github/Myriad-Dreamin/golang-pack`, it will be processed as `github/Myriad-Dreamin/golang-pack/cmd/generate/model-definitions`

+ output `str`: a package path that we can visit by go module. it is relative to `package`. e.g. :

    + `generated/model-definitions`. if `package` is `github/Myriad-Dreamin/golang-pack`, it will be processed as `github/Myriad-Dreamin/golang-pack/cmd/generate/model-definitions`

+ local_toolset `str`: filepath to golang toolset, the toolset's package name must be `github.com/Myriad-Dreamin/golang-pack`

+ module `ModuleConfig`: see `ModuleConfig`

+ parse `ParseConfig`: see `ParseConfig`

+ name `str`: name of project

+ version `str`: version of project

+ description `str`: description of project

ModuleConfig:

+ loaders `[]LoaderConfig`: preprocessors of project file, see `LoaderConfig`

LoaderConfig:

+ test `str | re.Pattern`: test a absolute file path, and use loader if matched.

+ target: `str`: the output filepath, e.g.:

    + `[file-name].go`. here `file-name` is the base name of source file without any extension

    + `@/path/to/generated_file_root/[file-name].go`. here `@` is the absolute path to project root.

    + `[file-name]-[hash:8].go`. here `hash` is the md5 hash of source file

+ use: `Loader | type(Loader) | str`: loader to be used if a file is matched with this item

## Loader Example:

the input of loader's function handler is a golang function ast. we can process it and return multiple statements. a simple generate function looks like this:

```python
def stub_get_id(self, context: Context, lhs: List[Stmt], rhs: List[Stmt]):
    assert len(rhs) == 0
    assert len(lhs) == 1

    # get any ast property if needed
    id_name = lhs[0].ident.name.title()

    res = self.must_create_context(context, [])
    res = self.must_create_ok_decl(context, res)
    context.context_vars[id_name] = Object.create(id_name, 'uint')

    # you can simply ignore the expression type, and just append a code fragment to avoid unnecessary work
    res.append(OpaqueExp.create(f"context.{id_name}, ok = snippet.ParseUint(c, {context.fn.recv.name}.key)"))
    res.append(OpaqueExp.create("if !ok {\nreturn\n}"))

    return None, res
```

the Golang AST class definitions are located in [go-ast definitions](https://github.com/Myriad-Dreamin/golang-pack/blob/main/go_ast/__init__.py)

for example, a stub loader which has around 400 LOC, can process a file with controller methods from:

```go

func (svc Sc) PostSubmission(c controller.MContext) {

	id := svc.Binder.GetID()
	var request = new(api.PostSubmissionRequest)
	svc.Binder.Bind(request)

	svc.Binder.AbortIfHint(request.Language == "", types.CodeBindError)

	var response *api.GetSubmissionReply
	var s = new(submission.Submission)

	svc.Binder.Context(s).Serve(id, request, response).CatchRef(func(err error) {
		svc.logStash.Info("Serve request failed", "context", c, "data", request, "err", err)
	}).Then(func() {
		c.JSON(http.StatusOK, response)
	})

	svc.Binder.ServeKeyed("PostDo", id, response)
}
```

to:

```go
type PostSubmissionContext struct {
	Id       uint
	Request  *api.PostSubmissionRequest
	S        *submission.Submission
	Response *api.GetSubmissionReply
}

type PostSubmissionSelfService interface {
	PostSubmission(context *PostSubmissionContext) (err error)
}

type PostSubmissionPostDoService interface {
	PostDo(context *PostSubmissionContext) (err error)
}

type PostSubmissionService interface {
	PostSubmissionSelfService
	PostSubmissionPostDoService
}

func (svc Sc) PostSubmission(c controller.MContext) {
	var context PostSubmissionContext
	var ok bool
	context.Id, ok = snippet.ParseUint(c, svc.key)
	if !ok {
		return
	}
	var request = new(api.PostSubmissionRequest)
	context.Request = request
	if !snippet.BindRequest(c, request) {
		return
	}
	if request.Language == "" {
		snippet.DoReportHintRaw(c, "Assertion Failed: want request.Language == \"\"", types.CodeBindError)
		return
	}
	var response *api.GetSubmissionReply
	var s = new(submission.Submission)
	context.S = s
	var err error
	if err = svc.resolver.Require(svc.serviceName).(PostSubmissionSelfService).PostSubmission(&context); err != nil {
		svc.logStash.Info("Serve request failed", "context", c, "data", request, "err", err)

		snippet.DoReport(c, err)
		return
	} else {
		request = context.Request
		response = context.Response
		c.JSON(http.StatusOK, response)

	}
	if err = svc.resolver.Require(svc.serviceName).(PostSubmissionPostDoService).PostDo(&context); err != nil {

		snippet.DoReport(c, err)
		return
	} else {
		response = context.Response

	}
}
```

## Philosophy

you should not use loader to process go file if it is unnecessary.

package main

import (
	"bytes"
	"fmt"
	"github.com/Myriad-Dreamin/minimum-lib/sugar"
	"go/ast"
	"go/build"
	"go/parser"
	"go/printer"
	"go/token"
	"gopkg.in/yaml.v3"
	"os"
	"path/filepath"
	"reflect"
	"sort"
	"strings"
	"sync"
)

func parseDir(fileDir string, fset *token.FileSet, mode parser.Mode) (_ *ast.Package, err error) {
	if fset == nil {
		fset = token.NewFileSet()
	}

	var pkgs map[string]*ast.Package
	pkgs, err = parser.ParseDir(fset, fileDir, nil, mode)
	if err != nil {
		return
	}

	switch len(pkgs) {
	case 3:
		for _, v := range pkgs {
			if strings.HasSuffix(v.Name, "_test") || v.Name == "main" {
				continue
			}
			return v, nil
		}
	case 2:
		for _, v := range pkgs {
			if strings.HasSuffix(v.Name, "_test") {
				continue
			}
			return v, nil
		}
	case 1:
		for _, v := range pkgs {
			return v, nil
		}
	default:
		err = fmt.Errorf("invalid parsed package result: %v", pkgs)
		return
	}

	err = fmt.Errorf("invalid unwrap package result: %v", pkgs)
	return nil, nil
}

func parsePkg(pkgName string, fset *token.FileSet, mode parser.Mode) (_ *ast.Package, err error) {

	srcDir, err := filepath.Abs(pkgName)
	if err != nil {
		return
	}
	pkg, err := build.Import(pkgName, srcDir, 0)
	if err != nil {
		return
	}

	return parseDir(pkg.Dir, fset, mode)
}

type generator struct {
	mutex sync.Mutex

	stubObject         *ast.Object
	stubVariableObject *ast.Object

	fileSet  *token.FileSet
	packages map[string]*ast.Package
}

type FilePos struct {
	File   int `yaml:"f"`
	Line   int `yaml:"l"`
	Column int `yaml:"c"`
	Offset int `yaml:"o"`
	Length int `yaml:"s"`
}

type ImportStmt struct {
	FilePos FilePos `yaml:"p"`
	Alias   string  `yaml:"alias"`
	Path    string  `yaml:"path"`
}

type Obj struct {
	Name string `yaml:"n"`
	Type string `yaml:"t"`
}

type Stmt interface {
	GetPos() *FilePos
}

const (
	ExpTypeBinary    = "b"
	ExpTypeUnary     = "u"
	ExpTypeCall      = "c"
	ExpTypeOpaque    = "o"
	ExpTypeAssign    = "a"
	ExpTypeBlock     = "k"
	ExpTypeSelect    = "s"
	ExpTypeIf        = "i"
	ExpTypeIdent     = "id"
	ExpTypeTypeSpec  = "t"
	ExpTypeValueSpec = "v"
	ExpTypeSelector  = "l"
)

type BaseExp struct {
	Pos  FilePos `yaml:"p"`
	Type string  `yaml:"t"`
}

func (b *BaseExp) GetPos() *FilePos {
	return &b.Pos
}

type BlockExp struct {
	BaseExp `yaml:",inline"`
	Block   []Stmt `yaml:"b"`
}

func createBlock(block []Stmt) Stmt {
	return &BlockExp{BaseExp: BaseExp{Type: ExpTypeBlock}, Block: block}
}

func createSelect(block []Stmt) Stmt {
	return &BlockExp{BaseExp: BaseExp{Type: ExpTypeSelect}, Block: block}
}

type SelectorExp struct {
	BaseExp  `yaml:",inline"`
	X Stmt   `yaml:"x"`
	Sel     string `yaml:"n"`
}

func createSelector(x Stmt, sel string) Stmt {
	return &SelectorExp{BaseExp: BaseExp{Type: ExpTypeSelector}, X: x, Sel: sel}
}

type GenExp struct {
	BaseExp `yaml:",inline"`
	Spec    []Stmt `yaml:"s"`
}

func createGen(s string, spec []Stmt) Stmt {
	return &GenExp{
		BaseExp: BaseExp{Type: s},
		Spec:    spec,
	}
}

type AssignExp struct {
	BaseExp `yaml:",inline"`
	Lhs     []Stmt `yaml:"l"`
	Rhs     []Stmt `yaml:"r"`
}

func createAssign(lhs, rhs []Stmt) Stmt {
	return &AssignExp{BaseExp: BaseExp{Type: ExpTypeAssign}, Lhs: lhs, Rhs: rhs}
}

type OpaqueExp struct {
	BaseExp `yaml:",inline"`
	Opaque  string `yaml:"o"`
}

func createOpaque(o string) Stmt {
	return &OpaqueExp{BaseExp: BaseExp{Type: ExpTypeOpaque}, Opaque: o}
}

type TypeSpecExp struct {
	BaseExp  `yaml:",inline"`
	Name     string `yaml:"n"`
	TypeSpec Stmt   `yaml:"ts"`
}

func createTypeSpec(name string, t Stmt) Stmt {
	return &TypeSpecExp{BaseExp: BaseExp{Type: ExpTypeTypeSpec}, Name: name, TypeSpec: t}
}

type ValueSpecExp struct {
	BaseExp  `yaml:",inline"`
	Names    []string `yaml:"l"`
	Values   []Stmt   `yaml:"r"`
	TypeSpec Stmt     `yaml:"ts"`
}

func createValueSpec(names []string, t Stmt, rhs []Stmt) Stmt {

	return &ValueSpecExp{BaseExp: BaseExp{Type: ExpTypeValueSpec}, Names: names, TypeSpec: t, Values: rhs}
}

type IdentExp struct {
	BaseExp `yaml:",inline"`
	Obj     `yaml:"o"`
}

func createIdent(obj Obj) Stmt {
	return &IdentExp{BaseExp: BaseExp{Type: ExpTypeIdent}, Obj: obj}
}

type BinaryExp struct {
	BaseExp  `yaml:",inline"`
	Operator string `yaml:"o"`
	Lhs      Stmt   `yaml:"l"`
	Rhs      Stmt   `yaml:"r"`
}

func createBinary(o string, l, r Stmt) Stmt {
	return &BinaryExp{BaseExp: BaseExp{Type: ExpTypeBinary}, Operator: o, Lhs: l, Rhs: r}
}

type IfExp struct {
	BaseExp `yaml:",inline"`
	Init    Stmt   `yaml:"i"`
	Cond    Stmt   `yaml:"c"`
	Else    Stmt   `yaml:"e"`
	Body    []Stmt `yaml:"b"`
}

func createIf(i, c, e Stmt, b []Stmt) Stmt {
	return &IfExp{BaseExp: BaseExp{Type: ExpTypeIf}, Init: i, Cond: c, Else: e, Body: b}
}

type UnaryExp struct {
	BaseExp  `yaml:",inline"`
	Operator string `yaml:"o"`
	Lhs      Stmt   `yaml:"l"`
}

func createUnary(o string, l Stmt) Stmt {
	return &UnaryExp{BaseExp: BaseExp{Type: ExpTypeUnary}, Operator: o, Lhs: l}
}

type CallExp struct {
	BaseExp  `yaml:",inline"`
	Callee   Stmt   `yaml:"c"`
	Variadic bool   `yaml:"v"`
	In       []Stmt `yaml:"i"`
}

func createCall(callee Stmt, isV token.Pos, in []Stmt) Stmt {
	return &CallExp{BaseExp: BaseExp{Type: ExpTypeCall}, Variadic: isV != token.NoPos, Callee: callee, In: in}
}

type FuncDesc struct {
	Pos  FilePos `yaml:"p"`
	Recv Obj     `yaml:"r"`
	Name string  `yaml:"n"`
	In   []Obj   `yaml:"in"`
	Out  []Obj   `yaml:"out"`
	Body Stmt    `yaml:"body"`
}

type DumperContext struct {
	fileSet *token.FileSet `yaml:"-"`
	pkg     *ast.Package   `yaml:"-"`

	RevFilesMapping map[string]int `yaml:"-"`
	FilesMapping    map[int]string `yaml:"file_mapping"`

	ImportStmts      []ImportStmt `yaml:"imports"`
	FuncDescriptions []FuncDesc   `yaml:"functions"`
}

func (d *DumperContext) ToPos(pos ast.Node) FilePos {
	position := d.fileSet.Position(pos.Pos())
	return FilePos{
		File:   d.RevFilesMapping[position.Filename],
		Line:   position.Line,
		Column: position.Column,
		Offset: position.Offset,
		Length: d.fileSet.Position(pos.End()).Offset - position.Offset,
	}
}

func (d *DumperContext) Visit(node ast.Node) (w ast.Visitor) {
	switch n := node.(type) {
	case *ast.ImportSpec:
		var alias string
		if n.Name != nil {
			alias = n.Name.String()
		}

		d.ImportStmts = append(d.ImportStmts, ImportStmt{
			FilePos: d.ToPos(n),
			Alias:   alias,
			Path:    n.Path.Value[1 : len(n.Path.Value)-1],
		})
	case *ast.FuncDecl:
		//n.Name
		var fn FuncDesc
		fn.Pos = d.ToPos(n)

		for _, r := range n.Recv.List {
			fn.Recv = Obj{
				Name: r.Names[0].Name,
				Type: d.stringifyNode(r.Type),
			}
		}

		fn.Name = n.Name.Name

		if n.Type.Params != nil {
			for _, ps := range n.Type.Params.List {
				var o Obj
				o.Type = d.stringifyNode(ps.Type)

				for _, pn := range ps.Names {
					o.Name = pn.Name
					fn.In = append(fn.In, o)
				}
			}
		}

		if n.Type.Results != nil {

			for _, ps := range n.Type.Results.List {
				var o Obj
				o.Type = d.stringifyNode(ps.Type)

				for _, pn := range ps.Names {
					o.Name = pn.Name
					fn.Out = append(fn.Out, o)
				}
			}
		}

		fn.Body = d.parseStmt(n.Body)

		d.FuncDescriptions = append(d.FuncDescriptions, fn)
	}

	return d
}
func (d *DumperContext) stringifyNode(expr ast.Node) string {
	var b = bytes.NewBuffer(make([]byte, 0, 10))
	sugar.HandlerError0(printer.Fprint(b, d.fileSet, expr))
	return b.String()
}

func (d *DumperContext) parseStmt(stmt ast.Stmt) Stmt {
	var s = d.parseStmt_(stmt)
	*s.GetPos() = d.ToPos(stmt)
	return s
}

func (d *DumperContext) parseDeclExp(decl ast.Decl) Stmt {
	var s = d.parseDeclExp_(decl)
	//*s.GetPos() = d.ToPos(decl)
	return s
}

func (d *DumperContext) parseExp(x ast.Expr) Stmt {
	var s = d.parseExp_(x)
	*s.GetPos() = d.ToPos(x)
	return s
}

func (d *DumperContext) parseSpec(spec ast.Spec) Stmt {
	var s = d.parseSpec_(spec)
	*s.GetPos() = d.ToPos(spec)
	return s
}

func (d *DumperContext) parseStmt_(stmt ast.Stmt) Stmt {
	switch stmt := stmt.(type) {
	case *ast.IncDecStmt:
		return createUnary(
			stmt.Tok.String(), d.parseExp(stmt.X))
	case *ast.SendStmt:
		return createOpaque(d.stringifyNode(stmt))
	case *ast.ExprStmt:
		return d.parseExp(stmt.X)
	case *ast.AssignStmt:
		var lhs, rhs []Stmt
		for _, l := range stmt.Lhs {
			lhs = append(lhs, d.parseExp(l))
		}
		for _, r := range stmt.Rhs {
			rhs = append(rhs, d.parseExp(r))
		}

		return createAssign(lhs, rhs)
	case *ast.SelectStmt:
		var block []Stmt
		if stmt.Body != nil {
			for _, b := range stmt.Body.List {
				block = append(block, d.parseStmt(b))
			}
		}

		return createSelect(block)
	case *ast.BlockStmt:
		var block []Stmt
		if stmt != nil {
			for _, b := range stmt.List {
				block = append(block, d.parseStmt(b))
			}
		}

		return createBlock(block)
	case *ast.IfStmt:
		var block []Stmt
		if stmt.Body != nil {
			for _, b := range stmt.Body.List {
				block = append(block, d.parseStmt(b))
			}
		}

		return createIf(d.parseStmt(stmt.Init), d.parseExp(stmt.Cond), d.parseStmt(stmt.Else), block)
	case *ast.DeclStmt:
		return d.parseDeclExp(stmt.Decl)
	case *ast.ForStmt:
		return createOpaque(d.stringifyNode(stmt))
	case *ast.DeferStmt:
		return createOpaque(d.stringifyNode(stmt))
	case *ast.GoStmt:
		return createOpaque(d.stringifyNode(stmt))
	case *ast.RangeStmt:
		return createOpaque(d.stringifyNode(stmt))
	case *ast.TypeSwitchStmt:
		return createOpaque(d.stringifyNode(stmt))
	case *ast.SwitchStmt:
		return createOpaque(d.stringifyNode(stmt))

	case *ast.EmptyStmt:
		return createOpaque(d.stringifyNode(stmt))
	case *ast.LabeledStmt:
		return createOpaque(d.stringifyNode(stmt))
	case *ast.ReturnStmt:
		return createOpaque(d.stringifyNode(stmt))
	case *ast.BranchStmt:
		return createOpaque(d.stringifyNode(stmt))
	case *ast.BadStmt:
		return createOpaque("")
	default:
		panic("want process " + reflect.TypeOf(stmt).String())
	}
}

func (d *DumperContext) parseDeclExp_(decl ast.Decl) Stmt {
	switch decl := decl.(type) {
	case *ast.GenDecl:
		var specs []Stmt
		for _, rawSpec := range decl.Specs {
			specs = append(specs, d.parseSpec(rawSpec))
		}

		return createGen(decl.Tok.String(), specs)
	case *ast.FuncDecl:
		panic("want process " + reflect.TypeOf(decl).String())
	case *ast.BadDecl:
		panic("want process " + reflect.TypeOf(decl).String())
	default:
		panic("want process " + reflect.TypeOf(decl).String())
	}
}

func (d *DumperContext) parseExp_(x ast.Expr) Stmt {
	switch exp := x.(type) {
	case *ast.SelectorExpr:
		return createSelector(d.parseExp(exp.X), exp.Sel.Name)
	case *ast.Ident:
		if exp.Obj == nil || exp.Obj.Type == nil {
			return createIdent(Obj{Type: "", Name: exp.Name})
		} else {
			return createIdent(Obj{Type: d.stringifyNode(exp.Obj.Type.(ast.Node)), Name: exp.Name})
		}
	case *ast.BasicLit:
		return createOpaque(d.stringifyNode(exp))

	case *ast.CallExpr:
		var block []Stmt
		if exp.Args != nil {
			for _, b := range exp.Args {
				block = append(block, d.parseExp(b))
			}
		}

		return createCall(
			d.parseExp(exp.Fun), exp.Ellipsis, block)
	case *ast.BinaryExpr:
		return createBinary(
			exp.Op.String(), d.parseExp(exp.X), d.parseExp(exp.Y))
	case *ast.FuncLit:
		return createOpaque(d.stringifyNode(exp))
	case *ast.StarExpr:
		return createOpaque(d.stringifyNode(exp))
	case *ast.UnaryExpr:
		return createUnary(
			exp.Op.String(), d.parseExp(exp.X))
	case *ast.IndexExpr:
		return createOpaque(d.stringifyNode(exp))
	case *ast.SliceExpr:
		return createOpaque(d.stringifyNode(exp))

	case *ast.KeyValueExpr:
		return createOpaque(d.stringifyNode(exp))
	case *ast.ParenExpr:
		return createOpaque(d.stringifyNode(exp))
	case *ast.TypeAssertExpr:
		return createOpaque(d.stringifyNode(exp))
	case *ast.BadExpr:
		panic("want process " + reflect.TypeOf(exp).String())
	default:
		panic("want process " + reflect.TypeOf(exp).String())
	}
}

func (d *DumperContext) parseSpec_(spec ast.Spec) Stmt {
	switch spec := spec.(type) {
	case *ast.ValueSpec:
		var names []string
		for _, name := range spec.Names {
			names = append(names, name.Name)
		}
		var ts Stmt
		if spec.Type != nil {
			ts = d.parseExp(spec.Type)
		}

		var rhs []Stmt
		for _, v := range spec.Values {
			rhs = append(rhs, d.parseExp(v))
		}

		return createValueSpec(names, ts, rhs)
	case *ast.TypeSpec:
		return createTypeSpec(spec.Name.Name, d.parseExp(spec.Type))
	case *ast.ImportSpec:
		panic("invalid stmt " + reflect.TypeOf(spec).String())
	default:
		panic("want process " + reflect.TypeOf(spec).String())
	}
}

type NullReader struct{}

func (n2 NullReader) Write(p []byte) (n int, err error) {
	return len(p), nil
}

func main() {
	var pkgName, cachePath string
	if len(os.Args) == 1 {
		pkgName = "github.com/Myriad-Dreamin/boj-v6/cmd/generate/controller_binding/inner/model"
		cachePath = ".cache/ast_dump"
	} else {
		pkgName, cachePath = os.Args[1], os.Args[2]
	}

	var fileSet = token.NewFileSet()

	pkg, err := parsePkg(pkgName, fileSet, parser.ParseComments|parser.DeclarationErrors)
	sugar.HandlerError0(err)

	var s []string
	for k := range pkg.Files {
		s = append(s, k)
	}

	dumperContext := &DumperContext{
		fileSet:         fileSet,
		pkg:             pkg,
		RevFilesMapping: map[string]int{},
		FilesMapping:    map[int]string{},
	}

	sort.Strings(s)
	for i := range s {
		dumperContext.RevFilesMapping[s[i]] = i
		dumperContext.FilesMapping[i] = s[i]
	}

	//g := &generator{fileSet: fileSet, packages: map[string]*ast.Package{
	//	pkgName: pkg,
	//}}
	//
	//g.parseAllImports([]interface{}{g.resolveBuiltIn()})

	//fileSet.Iterate(func(file *token.File) bool {
	//
	//})

	//for k, v := range g.packages {
	//	fmt.Println(k, v)
	//}

	ast.Walk(dumperContext, pkg)

	var path = filepath.Join(cachePath, pkgName)
	sugar.HandlerError0(os.MkdirAll(filepath.Dir(path), 0666))
	var f *os.File
	f, err = os.OpenFile(path, os.O_WRONLY|os.O_CREATE, 0666)
	sugar.HandlerError0(err)
	defer f.Close()

	e := yaml.NewEncoder(f)
	e.SetIndent(2)
	sugar.HandlerError0(e.Encode(dumperContext))
}

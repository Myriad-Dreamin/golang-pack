package main

import (
	"github.com/Myriad-Dreamin/minimum-lib/sugar"
	"go/ast"
	"go/parser"
)

func (g *generator) resolveBuiltIn() *ast.Package {

	pkgName := "builtin"
	pkg, err := parsePkg(pkgName, g.fileSet, parser.ParseComments|parser.DeclarationErrors)
	sugar.HandlerError0(err)
	return pkg
}

func (g *generator) resolvePackageObject(file *ast.File) {
	i := 0
	for _, ident := range file.Unresolved {
		var resolved = false

		for _, importSpec := range file.Imports {
			if importSpec.Name != nil && importSpec.Name.Name == ident.Name {
				ident.Obj = ast.NewObj(ast.Pkg, importSpec.Name.Name)
				ident.Obj.Decl = importSpec
				resolved = true
				break
			}
		}

		if !resolved {
			file.Unresolved[i] = ident
			i++
		}
	}
	file.Unresolved = file.Unresolved[0:i]
}

package main

import (
	"go/ast"
	"go/build"
	"go/parser"
	"sync"
)

func (g *generator) parseAllImports(opts []interface{}) {

	if len(g.packages) != 1 {
		panic("len 1")
	}

	var pkg *ast.Package
	for _, v := range g.packages {
		pkg = v
	}

	for i := range opts {
		switch opt := opts[i].(type) {
		case *ast.Package:
			g.packages["builtin"] = opt
		}
	}

	g.parseImports(pkg, 0)

	if pkg != nil {

		for _, f := range pkg.Files {
			if len(f.Unresolved) != 0 {
				panic("unresolved target")
			}
		}
	}

	//if !resolveSerial(stubPkg, "Stub", &g.stubObject) {
	//	panic("unresolved stub")
	//}

}

func (g *generator) parseImports(pkg *ast.Package, depth int) {
	if depth > 0 {
		return
	}

	var wg sync.WaitGroup
	var mu sync.Mutex

	for _, file := range pkg.Files {
		mu.Lock()
		g.resolvePackageObject(file)
		mu.Unlock()

		wg.Add(len(file.Imports))
		for _, importSpec := range file.Imports {
			value := importSpec.Path.Value[1 : len(importSpec.Path.Value)-1]

			switch value {
			case "C":
				wg.Done()
				continue
			}
			g.mutex.Lock()
			subPkg, ok := g.packages[value]
			g.mutex.Unlock()

			if !ok {
				depPkg, err := parsePkg(value, g.fileSet, parser.ParseComments|parser.DeclarationErrors)
				if err != nil {
					if _, ok := err.(*build.NoGoError); !ok {
						panic(err)
					}
					wg.Done()
					continue
				}

				g.mutex.Lock()
				g.packages[value] = depPkg
				g.mutex.Unlock()
				go func(file *ast.File, importSpec *ast.ImportSpec) {
					g.parseImports(depPkg, depth+1)

					mu.Lock()
					resolveFileImports(file, importSpec, depPkg)
					mu.Unlock()

					wg.Done()
				}(file, importSpec)

			} else {
				_ = subPkg

				go func(file *ast.File, importSpec *ast.ImportSpec) {

					mu.Lock()
					resolveFileImports(file, importSpec, subPkg)
					mu.Unlock()

					wg.Done()
				}(file, importSpec)
			}
		}

		mu.Lock()
		resolveFileImports(file, nil, g.packages["builtin"])
		mu.Unlock()
	}
	wg.Wait()
}


func resolveSerial(pkg *ast.Package, name string, target **ast.Object) (resolved bool) {
	for _, depFile := range pkg.Files {
		if obj := depFile.Scope.Lookup(name); obj != nil {
			*target = obj
			resolved = true
			return
		}
	}
	return
}

func resolveFileImports(file *ast.File, importSpec *ast.ImportSpec, pkg *ast.Package) {

	if importSpec != nil {
		var i int

		for _, ident := range file.Unresolved {
			if pkg.Name == ident.Name {
				ident.Obj = ast.NewObj(ast.Pkg, pkg.Name)
				ident.Obj.Decl = importSpec
			} else {
				file.Unresolved[i] = ident
				i++
			}
		}

		file.Unresolved = file.Unresolved[0:i]
		i = 0
	}

	var i int

	for _, ident := range file.Unresolved {
		if !resolveSerial(pkg, ident.Name, &ident.Obj) {
			file.Unresolved[i] = ident
			i++
		}
	}

	file.Unresolved = file.Unresolved[0:i]
}

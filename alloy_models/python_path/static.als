/* Paths and Filesystem Entries */

abstract sig Entry {}
one sig Directory extends Entry {}
one sig File extends Entry {}

abstract sig AnyPath {}
one sig RootPath extends AnyPath {}
sig Path extends AnyPath {
	, parent: AnyPath
	, state: Root -> lone Entry
}

fact "paths form a tree" {
	no p: Path | p in p.^parent
	all p: Path | RootPath in p.^parent
}

fact "fanout is limited (to make viewing easy)" {
	all p: AnyPath | #(p.~parent) <=3
}

fact "we can ignore unused paths" {
	all p: Path | eventually {
		 some p.state
	}
}

fun children[p: Path]: set Path {
	p.~parent
}

fun descendants[p: Path]: set Path {
	p.^~parent
}

/* Root (a search path root) */


sig Root {}

fun directories[r: Root]: set Path {
	state.Directory.r
}
fun files[r: Root]: set Path {
	state.File.r
}
fun paths[r: Root]: set Path {
	directories[r] + files[r]
}
fun entry[r: Root, p: Path]: lone Entry {
	r.(p.state)
}


pred root_is_valid[r: Root] {
	no (r.directories & r.files)
	(r.paths.parent - RootPath) in r.directories
}

pred all_roots_are_valid {
	all r: Root | root_is_valid[r]
}

fact "All roots are valid" { all_roots_are_valid }


run {} for 5 but 2 Root

/* Paths and Filesystem Entries */

abstract sig Entry {}
one sig Directory extends Entry {}
one sig File extends Entry {}

abstract sig AnyPath {}
one sig RootPath extends AnyPath {}
sig Path extends AnyPath {
	, parent: AnyPath
	, var state: Root -> lone Entry
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

fact "All roots are initially valid" { all_roots_are_valid }
fact "All roots are initially empty" { no state }

/* Filesystem dynamics */

pred stutter {
	state' = state
}

pred new[r: Root, p: Path, e: Entry] {
	no r.(p.state)
	p.parent in (directories[r] + RootPath)
	state' = state + p->r->e
}

pred remove_file[r: Root, p: Path] {
	p in files[r]
	and state' = state - p->r->File
}

pred remove_tree[r: Root, p: Path] {
	p in directories[r]
	let to_remove = p + descendants[p] {
		state' = state - to_remove->r->Entry
	}
}


pred filesystem_event {
	some r: Root, p: Path |
		remove_file[r, p]
		or
		remove_tree[r, p]
		or
		new[r, p, File]
		or
		new[r, p, Directory]
}


fact traces {
	always {
		filesystem_event
		or stutter
	}
	// convergence
	stutter implies after {stutter}
	// progress
	eventually { filesystem_event }
}


/* Assertions */


// check { always { all_roots_are_valid } } for 5 but 2 Root

run { eventually { all r: Root { #(paths[r]) >= 3 } }} for 5 but exactly 2 Root

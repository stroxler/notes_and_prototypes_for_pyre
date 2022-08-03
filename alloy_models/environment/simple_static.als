open util/ordering[Key] as key_ordering
open util/ordering[Layer] as layer_ordering


sig Layer{}

sig  Key {
	, layer: Layer
	, value : lone Value
	, depends : set Key
}
sig Value {}


fact "Layers partition keys" {
	Key.layer = Layer
}

fact "Orderings are canonical" {
	all k0, k1: Key {
		k1.layer in k0.layer.nexts implies k1 in k0.nexts
	}
}

fact "Dependencies are ordered" {
	all k0, k1: Key {
		k0 in k1.depends implies k0.layer in k1.layer.prevs
	}
}

fact "Computations have dependencies" {
	all k: Key {
		k.layer = Layer <: first
		or some k.depends
	}
}


run {} for 5 but 3 Layer

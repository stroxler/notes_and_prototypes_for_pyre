/*
Model for a one-shot update to an environment stack

The current status is that I cannot seem to enforce a restriction that
only one layer is updated at a time - somehow my preconditions are too
restrictive given the configuration constraints. I'm not sure yet why this is.

Moreover, my intended restriction that only the first layer can have values
with no compute dependencies does not appear to be working - I'm seeing
examples where Layer1 gets a value that is computed from nothing.

My guess is that part of the problem is needing time-based constraints in
too many places; if I could link values to layers statically then I could express
constraints in a simpler and less error-prone way.
*/


open util/ordering[Layer] as layer_ordering
// the Key and Value orderings are mainly for readability, they aren't essential
open util/ordering[Key] as key_ordering
open util/ordering[Value] as value_ordering

sig Layer{}

sig  Key {
	, owning_layer: Layer
	, var value : lone Value
	, var dependencies : set Key
}
sig Value {
	, computed_from : set Key -> Value
}

sig Pair {
	, edge: Key one -> one Value
}



var one sig LastUpdatedLayer in Layer {}

fun keys_in_layers[layers: set Layer]: set Key {
	owning_layer.layers
}

fun values_in_layers[layer: set Layer]: set Value {
	keys_in_layers[layer].value
}

fun keys_pointing_to[v: set Value]: set Key {
	v.~value
}

fun currently_available_values[]: set Value {
	Key.value
}

fun currently_available_keys[]: set Key {
	value.Value
}

/*** restrictions on the configuration ***/

fact "Ordering is cannonical" {
	// key ordering respects layer ordering
	all k0, k1: Key {
		k0.owning_layer in k1.owning_layer.prevs implies k0 in k1.prevs
	}
	// ordering of values and keys is consistent in updates
	all p0, p1: Pair {
		let k0 = (p0.edge).Value, v0 = Key.(p0.edge) |
		let k1 = (p1.edge).Value, v1 = Key.(p1.edge) |
		k0 in k1.prevs implies v0 in v1.prevs
	}
	// value computations respect ordering
	all v0, v1: Value {
		v0 in Key.(v1.computed_from) implies v0 in v1.prevs
	}
}

fact "Each value is mapped to exactly one key" {
	all v: Value {
		one (Pair.edge).v
	}
}

fact "All values are eventually used" {
	all v : Value {
		eventually v in currently_available_values
	}
}

fact "All values except those in the first layer are computed from something" {
	all v: Value {
		no v.computed_from iff {
			eventually v in values_in_layers[Layer <: first]
		}
	}
}

/*** Initial state ***/

fact "Initially only the first layer has data" {
	no dependencies
	currently_available_keys.owning_layer = Layer <: first
	LastUpdatedLayer = Layer <: first
}

/*** transitions ***/

pred updateLayer[layer: one Layer, update_pairs: set Pair] {
	// the computation sweeps across layers, which we track using LastLayer
	layer.prev = LastUpdatedLayer
	LastUpdatedLayer' = layer
	
	let update = update_pairs.edge |
	let update_keys = update.Value |
	let update_values = Key.update |
	{
		// --- preconditions ---
		let upstream_layers = layer.prevs |
		let upstream_keys = keys_in_layers[upstream_layers] |
		let update_computed_from = update_values.computed_from |
		let used_keys = update_computed_from.Value |
		let used_values = Key.update_computed_from |
		{
			// update_keys.owning_layer = layer
			used_values in currently_available_values
			used_keys in upstream_keys
		}

		// --- postconditions ---
		all k: update_keys {
			k.value' = k.update
			k.dependencies' = k.dependencies + k.value'.computed_from.Value
		}

		// --- unchanged ---
		let unchanged_keys = (Key - update_keys) |
		{
			unchanged_keys.value' = unchanged_keys.value
			unchanged_keys.dependencies' = unchanged_keys.dependencies
		}
	}



}

pred stutter {
	value' = value
	dependencies' = dependencies
}

fact "transitions" {
	always {
		{
			some layer: Layer, update_pairs: Pair {
				updateLayer[layer, update_pairs]
			}
		} or {
			LastUpdatedLayer = (Layer <: last) and stutter
		}
	}
}


run { some k: Key | k not in keys_in_layers[Layer <: first] } for 3 but 2 Layer

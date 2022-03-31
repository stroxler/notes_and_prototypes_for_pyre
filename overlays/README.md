This directory contains some toy implementations of
an "environment stack" in python.

The goal is to illuminate some specific ideas for how to
structure the pyre ocaml code on a much smaller codebase.

One potential problem is that it isn't natural to capture
some of the structure of the ocaml code in python - in particular
the fact that as of March 2022 all of the environment caches
are globals, but we just need to keep the ocaml-specific restrictions in mind when looking at this.

The toy is simple in that the analysis propagated up the stack
is just "get a class's grandparents", and also the "python code"
we analyze doesn't use qualifiers but rather fully qualified names
so that we don't need any semantic analysis in our toy.

It is also simplified by the fact that dependencies only ever point
up one layer; this makes the python code simpler but doesn't really
affect validity for the present purposes.

The toy implementations are:
- `basic.py`: a nice idiomatic python representation of our
  env stack, with mutable updates and a dependency tree. Note
  that trying to implement overlays on this without thinking about
  the ocaml would be deceptively easy, since the caches are all
  first-class values whereas in ocaml they are not!
- `read_only.py`: adds an implementation of a read-only interface,
  which is very similar to our existing read-only environment where
  it just uses functions. The control flow is identical, but now
  `produce_value` is always a static method that take the read only
  as input.
- `read_only_overlay.py`: An implementation of overlays where we just
  intercept keys that belong to an overlaid module and construct a
  new read-only env stack from the existing read/write env. The
  overlay is read-only and has no push-based update. This implementation
  does not use a cache, but it would be easy to close over a cache
  when writing our `get` function if we wanted in-overlay caching;
  what we *can't* do easily is get push-based updates from this
  design, the overlay always has to be recomputed from the parent.


Dependencies are in a requirements file. To run tests:
```
py.test
```


# Use cases

Use case: Steven makes an unsaved edit to a.py. He should see type errors as he types.

Use case: Steven makes an unsaved edit to a.py and then another unsaved edit to a.py and another. Basically, he's typing code as usual. He should see type errors whenever the current state of the file has valid syntax.

Use case: Steven makes an unsaved edit to a.py and b.py. He then saves b.py. a.py should show errors corresponding to the saved version of b.py.

Use case: Steven makes an unsaved edit to a.py and presses `.` (or tries to hover or tries to use go-to-def). He should see auto-complete (or hover or go-to-def) information corresponding to the current unsaved state of the file.

Note: All of the above is how Hack works.

# Rough notes on "Why not Alternative X?"

## Approach: No caching at all

This will recompute `ast_env["b"]` every time we ask for a downstream element of the DAG, such as `class_grandparents_env["b.Foo"]`. This is too inefficient.

## Approach: Caching but no persistence

We throw away the overlay environment once we compute type errors.

This cannot support code-navigation features such as auto-complete or hover or go-to-def. They need to use the unsaved content of the file.

## Approach: Caching and persist the overlay environment, but recompute the overlay environment from scratch on a new edit or save

When a user is typing, we would need to recompute multiple times. This can be very expensive.

We might say that we will profile first and, if it is too slow, migrate to an updatable version later.

How hard will it be to migrate to an updatable version in this approach? This is a pull-based approach. To get the latest values after a new edit, we would need to invalidate the cache entries. Otherwise, we would just see the old entries. How would we invalidate cache entries correctly without recomputing everything?

I don't know of a way to invalidate caches in a pull-based approach. I suspect that we would have to give up on the pull-based approach and move to the push-based approach with dependency-filtering.

If this approach cannot be easily extended for better performance, we should use some other approach that is better suited.

# Proposed approach: Have two cache tables and use a push-based approach with dependency-filtering

Our environment stack represents a DAG of dependencies. With unsaved files, there are now two DAGs - one corresponding to the saved contents and one corresponding to the unsaved contents.

Proposal: Have two cache tables per environment. The first one is the existing cache table, containing all saved modules and their values. The second, new one just contains information about unsaved modules.

When pushing an unsaved file update, we filter dependencies so that only unsaved modules are updated. When pushing a saved file update, we propagate changes to all dependencies.

The above scheme means that an unsaved module will be represented twice, once in the saved table and once in the unsaved table. We need this because each environment operation has two variants: one that works on the original DAG and the other that works on the new DAG.

When getting a value that is not currently in cache: If the key is a saved module, we need to use the original environment (*even if* we depend on a key that is an unsaved module). Otherwise, we would end up making saved module values depend on unsaved module values. If the key is an unsaved module, we need to use the wrapper environment.

For example, suppose computing a value for an unsaved module `b` depends on a saved module class `a.X`, but `a.X` is uncached. In this case, we have to compute the value for `a.X` ... but in the original DAG. This is because we do not want `a.X` to use the unsaved values of any of its dependents. So, we may need to compute `b.XParent` - the parent of `a.X` - using the saved contents of `b`, even though `b` is unsaved. So, we need to keep both results around.

There is no need to wrap the cache table or do any pass-through. We will automatically look up or write to the correct table based on what the request is - whether the `get` call expects you to use the saved or unsaved values of your dependents and whether the `update` push call is

This design makes it easy to go for any of the other approaches - for example, if we want to recompute from scratch without persisting, we can disable the persistent cache table.

Note: This reuses the same push-based approach as regular file updates. It can thus easily invalidate old cache values when updating, unlike the previous overlay approach.

Note: The type and size of the extra cache needed is the same in both cases. So, if we would go with an in-memory cache for the persistent-overlay approach, we would do the same for persistent. If we would go with a pre-allocated shared memory table, we would do the same here.

Question: Have one wrapped environment for each unsaved file or one wrapped environment for all unsaved files?

Actually, once we have caching, we cannot have multiple environments. Otherwise, if we update the original environment independently, there would be nothing to tell the overlay environment to invalidate its cache.

So, we need to have one wrapped environment containing all unsaved files. Any updates, either to unsaved files or saved files, must go through this wrapped environment.

Note: In the toy `wrap_memory.py`, we modify the set of dependencies in the original environment. This does not affect correctness, but can make us update unnecessary dependencies in the future. That should be ok, but we can always optimize that by tracking unsaved dependencies in the wrapper cache table.

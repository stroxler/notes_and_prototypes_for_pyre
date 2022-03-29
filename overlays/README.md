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

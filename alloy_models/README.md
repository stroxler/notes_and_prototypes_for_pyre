# Some alloy notes, in particular where the footguns are

If you specify `for 1..1 steps` - which is convenient when trying to
build an initital dynamic model - and then add a progress condition to
your dynamics (i.e. you have a stutter operation and you require that
we don't always stutter) then your predicates will be inconsistent. This
is because with 1..1 steps, only stuttering is possible!

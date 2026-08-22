"""Settlement Truth Engine -- the matching cascade.

Deliberately imports nothing from the engine package -- not the generator,
not the simulator, and not the isolated answer key. The solver reimplements
what it needs; sharing code with the generator would make the two agree by
construction rather than by evidence.
"""

from .cascade import CascadeResult, run  # noqa: F401

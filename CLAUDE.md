# Claude Code Guidelines

## Typing

- **Never use `Any`.** Every value must have a precise, concrete type. Use `TypedDict`, `Protocol`, dataclasses, or union types instead of widening to `Any`.
- All functions and methods must have fully annotated signatures: every parameter and the return type.
- Prefer `str | None` over `Optional[str]` (use the `X | Y` union syntax throughout).
- Use `TypedDict` for structured dicts returned by or passed to external APIs (e.g. HTTP response payloads). Do not leave JSON payloads typed as `dict[str, Any]`.
- Use `Final` for module-level constants.
- Run `mypy --strict` (not just `--ignore-missing-imports`) as the standard; stubs or `py.typed` markers should be added where third-party libraries lack them.

## Functional Paradigm

- Prefer pure functions: a function should compute and return a value rather than mutate state as a side effect.
- Avoid mutable global state. Module-level mutable collections (e.g. `last_photo`, `last_audio`) should be replaced with explicit state passed through function arguments or encapsulated in a typed dataclass/class.
- Compose behaviour through function composition and higher-order functions rather than subclassing or inheritance.
- Prefer immutable data: use `tuple` over `list` when the collection does not need to grow, and frozen dataclasses where appropriate.

## Avoid Loops

- Do not use `for` or `while` loops. Replace them with:
  - `map()`, `filter()`, `functools.reduce()` for transformations and aggregations.
  - Generator expressions and list/dict/set comprehensions for projections.
  - `itertools` and `functools` from the standard library for more complex iteration patterns.
  - `next(...)` with a generator expression for finding the first matching element.
- This rule applies to both sync and async code.

## General

- Keep functions small and single-purpose.
- Errors should propagate as typed exceptions or explicit return types (`X | None`, result types), not be swallowed silently.
- All new code must pass `ruff check` and `mypy --strict` before being committed.

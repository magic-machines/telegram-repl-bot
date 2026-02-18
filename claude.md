# Functional Programming Guidelines

All code in this repository must follow a strict functional paradigm. These rules are non-negotiable.

---

## Type Signatures

Every function must carry an explicit, complete type signature. No `Any`. No implicit `Any` through missing annotations. No casting to `Any` as an escape hatch.

```python
# WRONG
def process(data):
    ...

def process(data: Any) -> dict:
    ...

# RIGHT
def process(data: bytes) -> Result[OcrText, ServiceError]:
    ...
```

Use `TypeVar`, `Generic`, and `Protocol` to express polymorphism. Use `TypeAlias` to name complex types. If you cannot express the type precisely, rethink the design — the type system is telling you something.

```python
A = TypeVar("A")
B = TypeVar("B")
E = TypeVar("E", bound=Exception)

type Result[A, E] = Ok[A] | Err[E]
type Predicate[A] = Callable[[A], bool]
type Morphism[A, B] = Callable[[A], B]
```

---

## No Loops

`for` and `while` are forbidden. Iteration is expressed through:

- List / dict / set comprehensions and generator expressions
- `map`, `filter`, `itertools.starmap`, `itertools.chain`, `itertools.takewhile`
- `functools.reduce` for left-folds
- Recursion with `@functools.cache` where memoisation is warranted
- `operator` module functions in place of inline lambdas

```python
# WRONG
results = []
for item in items:
    if item.valid:
        results.append(transform(item))

# RIGHT
results: list[Transformed] = [transform(item) for item in items if item.valid]

# WRONG
total = 0
for n in numbers:
    total += n

# RIGHT
total: int = functools.reduce(operator.add, numbers, 0)
```

---

## Typeclasses via Protocol

Model shared behaviour with `Protocol` (structural subtyping — duck-typed typeclasses). Never reach for inheritance to share an interface.

```python
from typing import Protocol, runtime_checkable

@runtime_checkable
class Functor(Protocol[A]):
    def fmap(self, f: Morphism[A, B]) -> "Functor[B]": ...

class Foldable(Protocol[A]):
    def fold(self, f: Callable[[B, A], B], initial: B) -> B: ...

class Serialisable(Protocol):
    def to_bytes(self) -> bytes: ...
    @classmethod
    def from_bytes(cls, raw: bytes) -> "Serialisable": ...
```

Define a protocol for every distinct capability. Concrete types satisfy protocols implicitly — no registration, no inheritance.

---

## Pattern Matching

Use `match` / `case` instead of `if / elif / else` chains over discriminated data. Every `match` must be exhaustive; add a `case _: assert_never(x)` arm when the type checker cannot prove exhaustiveness for you.

```python
from typing import assert_never

def handle_update(update: BotUpdate) -> Awaitable[None]:
    match update:
        case PhotoUpdate(file_id=fid, user=u):
            return enqueue_ocr(fid, u)
        case VoiceUpdate(file_id=fid, user=u):
            return enqueue_transcription(fid, u)
        case CommandUpdate(command="/start", user=u):
            return send_welcome(u)
        case CommandUpdate(command="/help", user=u):
            return send_help(u)
        case _:
            assert_never(update)
```

Match on structure, not on `isinstance` checks scattered through the body.

---

## Operators and Combinators

Prefer operator functions over inline lambdas. Compose pipelines with `functools.reduce(compose, [f, g, h])` or an explicit `pipe` combinator.

```python
import operator
from functools import reduce

def compose(*fns: Morphism) -> Morphism:
    """Right-to-left function composition: compose(f, g)(x) == f(g(x))"""
    return reduce(lambda f, g: lambda x: f(g(x)), fns)

def pipe(*fns: Morphism) -> Morphism:
    """Left-to-right application: pipe(f, g)(x) == g(f(x))"""
    return reduce(lambda f, g: lambda x: g(f(x)), fns)

# Usage
preprocess: Morphism[bytes, Image] = pipe(decode_bytes, correct_rotation, enhance_contrast)
```

Use `operator.attrgetter`, `operator.itemgetter`, `operator.methodcaller` in preference to ad-hoc lambdas.

---

## Objects as Data, Functions as Morphisms

Think in terms of **objects** (types / data shapes) and **morphisms** (pure functions between them). Every function is a morphism `A → B`. Side effects are morphisms into effect types.

- **Data** lives in `dataclass(frozen=True)` or `NamedTuple`. Mutation is forbidden.
- **Morphisms** are pure functions. A function that takes `X` and produces `Y` must not touch global state, mutate its arguments, or produce observable side effects outside of returning its value.
- **Effects** (I/O, async, exceptions) are expressed in return types: `Awaitable[B]`, `Result[B, E]`, `Iterator[B]`, `AsyncIterator[B]`.

```python
from dataclasses import dataclass

@dataclass(frozen=True)
class OcrRequest:
    file_id: str
    user_id: int

@dataclass(frozen=True)
class OcrText:
    content: str
    confidence: float

# Morphism: OcrRequest → Awaitable[Result[OcrText, ServiceError]]
async def run_ocr(req: OcrRequest) -> Result[OcrText, ServiceError]:
    ...
```

A function that silently swallows an error and returns `None` is not acceptable. Failure is a value — encode it in the return type.

---

## Result Type

Represent fallible computations with an explicit `Result` ADT. No bare `try / except` blocks that discard error information, and no functions whose failure mode is `None`.

```python
from dataclasses import dataclass

@dataclass(frozen=True)
class Ok[A]:
    value: A

@dataclass(frozen=True)
class Err[E]:
    error: E

type Result[A, E] = Ok[A] | Err[E]

def map_result(f: Morphism[A, B]) -> Morphism[Result[A, E], Result[B, E]]:
    def _apply(r: Result[A, E]) -> Result[B, E]:
        match r:
            case Ok(value=v):
                return Ok(f(v))
            case Err() as e:
                return e
    return _apply

def bind_result(f: Morphism[A, Result[B, E]]) -> Morphism[Result[A, E], Result[B, E]]:
    def _apply(r: Result[A, E]) -> Result[B, E]:
        match r:
            case Ok(value=v):
                return f(v)
            case Err() as e:
                return e
    return _apply
```

---

## Immutability

- No reassignment of local variables after binding.
- No mutation of containers passed as arguments.
- `dataclass(frozen=True)` for all domain objects.
- `tuple` and `frozenset` in preference to `list` and `set` when the collection is not consumed immediately.

---

## Purity and Side Effects

A function is pure if equal inputs always produce equal outputs with no observable side effects. Strive for a pure core; push I/O to the outermost layer.

- Async I/O belongs at the application boundary (bot handlers, HTTP endpoints).
- Business logic (OCR post-processing, transcription parsing, text formatting) must be pure and synchronous.
- Inject dependencies as function arguments rather than reading from module-level globals.

---

## What Good Code Looks Like Here

```python
from dataclasses import dataclass
from typing import Protocol, TypeVar, Callable
import functools, operator, itertools

A = TypeVar("A")
B = TypeVar("B")
E = TypeVar("E", bound=Exception)

type Morphism[A, B] = Callable[[A], B]
type Result[A, E] = Ok[A] | Err[E]

@dataclass(frozen=True)
class Ok[A]:
    value: A

@dataclass(frozen=True)
class Err[E]:
    error: E

@dataclass(frozen=True)
class ImageBytes:
    data: bytes

@dataclass(frozen=True)
class ProcessedImage:
    data: bytes
    rotation_degrees: float

@dataclass(frozen=True)
class OcrText:
    content: str

def correct_rotation(img: ImageBytes) -> ProcessedImage: ...
def enhance(img: ProcessedImage) -> ProcessedImage: ...
def extract_text(img: ProcessedImage) -> Result[OcrText, ValueError]: ...

pipeline: Morphism[ImageBytes, Result[OcrText, ValueError]] = pipe(
    correct_rotation,
    enhance,
    extract_text,
)
```

This is the expected shape of code in this repository: small, named, typed morphisms composed into pipelines, with data as frozen structures and failures as values.

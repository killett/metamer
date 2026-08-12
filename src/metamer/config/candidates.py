"""Candidate noise specifications, from a structured list or a sum expression.

**The structured list of term kinds is canonical and the string form desugars
to it.** `"white + matern12"` and `["white", "matern12"]` produce the same
`ProcessSpec`, which is asserted rather than assumed: the string form exists
because a TOML config is written by a person, and the moment two spellings can
disagree the config file stops being a faithful description of the run.

**DESUGARING IS RESTRICTED EVALUATION AGAINST THE REGISTRY, NOT A TOKENIZER AND
NOT `eval`.** Python's own parser reads the expression and the result is walked,
accepting exactly two node types: a bare name, and an addition of two accepted
nodes. Everything else -- a call, an attribute, a subscript, a number, a
subtraction -- is refused by name.

The three alternatives and why each is worse:

  - **`eval` with a restricted namespace** executes arbitrary syntax, and the
    restriction is a denylist of builtins rather than an allowlist of grammar.
    It also trips `S307`, correctly.
  - **A hand-rolled tokenizer** re-implements a parser that already exists and
    gets the edge cases wrong -- unbalanced parentheses, unicode identifiers,
    whitespace inside a name.
  - **`str.split("+")`** silently accepts `"white + + matern12"` and
    `"white+"`, producing an empty kind that the registry then reports as an
    unknown key, blaming the wrong thing.
"""

from __future__ import annotations

import ast
from collections.abc import Sequence

from metamer.core.registry import kernel_registry
from metamer.core.terms import ProcessSpec, TermSpec


def _kinds_from_expression(expression: str) -> list[str]:
    """Read the term kinds out of a sum expression, left to right.

    Args:
        expression: Something like `"white + matern12"`.

    Returns:
        The term kinds in source order. Order is not significant downstream --
        `ProcessSpec` sorts canonically at construction -- but it is preserved
        so an error message can name the offending position.

    Raises:
        ValueError: If the text does not parse, or parses to anything other
            than names joined by `+`.
    """
    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError as error:
        raise ValueError(
            f"candidate {expression!r} is not a valid term expression: {error.msg}. "
            "Write a sum of registered kernel names, e.g. 'white + matern12', "
            "or the equivalent list form ['white', 'matern12']"
        ) from error

    kinds: list[str] = []

    def walk(node: ast.expr) -> None:
        if isinstance(node, ast.Name):
            kinds.append(node.id)
            return
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
            walk(node.left)
            walk(node.right)
            return
        raise ValueError(
            f"candidate {expression!r} contains {type(node).__name__}, which is "
            "not permitted. A candidate is a sum of registered kernel names and "
            "nothing else -- no calls, attributes, subscripts or literals"
        )

    walk(tree.body)
    return kinds


def term_spec(kind: str) -> TermSpec:
    """Build a `TermSpec` for a registered family, at its declared defaults.

    Args:
        kind: Registry key naming the family.

    Returns:
        The term specification.

    Raises:
        KeyError: If `kind` is not registered. The registry's own message lists
            what is available, which is the fact a user needs.
    """
    family = kernel_registry[kind]()
    return TermSpec(
        kind=kind,
        params=family.param_specs(),
        ordering_param=getattr(family, "ordering_param", None),
    )


def parse_candidate(candidate: str | Sequence[str]) -> ProcessSpec:
    """Build a `ProcessSpec` from an expression or a list of term kinds.

    Args:
        candidate: `"white + matern12"` or `["white", "matern12"]`.

    Returns:
        The process specification, canonically ordered by its own constructor.

    Raises:
        ValueError: If the expression form is malformed, or the list form is
            empty. An empty candidate is a process with no terms, which has no
            likelihood; it is refused here rather than surfacing as a shape
            error inside the filter.
        KeyError: If any term kind is not registered.
    """
    kinds = (
        _kinds_from_expression(candidate)
        if isinstance(candidate, str)
        else list(candidate)
    )
    if not kinds:
        raise ValueError(
            f"candidate {candidate!r} names no terms; a noise model with no "
            "terms has no likelihood"
        )
    return ProcessSpec(tuple(term_spec(kind) for kind in kinds))

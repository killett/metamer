"""The tile write path: one region write per array, and the status invariant.

**THE INVARIANT IS CHECKED BEFORE THE WRITE, NOT AFTER.** A violated invariant
that reaches disk is already the defect, and a store is not cheaply readable back
mid-run. The check runs on the arrays **about to be written**, so a violation is
a refusal rather than a corrupted region -- and it is the same function Task 13's
exit criterion 4 runs over a finished store, so the two cannot drift apart.

**THREE EXEMPTIONS, EACH FOR A DIFFERENT REASON, ALL NAMED RATHER THAN IMPLIED
BY WHICH ARRAYS THE CHECKER HAPPENS TO LOOK AT:**

- **`/selection/` is exempt** because `outcome` has no `c` axis. A NaN delta-IC
  beside an `OK` status is legal and means "this criterion could not rank this
  point"; folding it into the outcome ladder would make a criterion-independent
  array depend on which criterion was requested.
- **`/primitives/iterations` is exempt** because a uint16 has no NaN. Its "no fit
  ran" value is 65535, and it feeds no arithmetic.
- **`/primitives/n_eff_trend` is exempt in the OK direction ONLY when the design
  has no trend column**, where NaN is its correct value rather than a defect.
  The caller states which, because the write path cannot tell a designed NaN
  from a bug without the design -- and a checker that guessed would be exempting
  a real failure at every point.

**FAILED CANDIDATES CARRY NaN, NEVER `-inf`.** `-inf` is a finite-looking
sentinel that survives an `isfinite` check downstream; it is the optimizer's
internal barrier value and must not reach the store.

**THE POINT-LEVEL OUTCOME'S RULE IS DEFINED HERE BECAUSE NOWHERE ELSE DEFINES
IT.** Design doc 12.2 lists `outcome[y,x]` as "aggregate" and never says
aggregate *how*. The rule: **`OK` if any candidate is `OK`** -- the point is
usable -- **otherwise `objective.merge_outcomes` over the per-model codes**,
which reports the earliest cause under the ladder already declared in
`OUTCOME_PRECEDENCE`. Reusing that ladder is what stops a second, inline
precedence being invented here; the `OK`-wins half is stated because the ladder
ranks `OK` last, so a bare merge would report a failure for a point that fitted.

**ONE REGION WRITE PER ARRAY PER TILE, AND NO WAY TO DECLINE.** There is
deliberately no "skip this tile" exit: a write path that can decline silently
makes the completion bitmap's meaning depend on which branch ran, and Task 10
sets the bit from the fact that this function returned.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Any

import numpy as np
import zarr
from numpy.typing import NDArray

from metamer.core.criteria import Criterion, rank_candidates
from metamer.core.objective import merge_outcomes
from metamer.core.outcomes import Outcome

if TYPE_CHECKING:  # pragma: no cover - typing only
    from metamer.batch.ragged import RaggedIndex
    from metamer.batch.tiling import Tile
    from metamer.core.fit import FitResult


class InvariantError(ValueError):
    """A status/value pairing the store forbids, caught before the write."""


def point_outcomes(outcome: NDArray[np.uint8]) -> NDArray[np.uint8]:
    """Aggregate per-model outcomes to one code per point.

    Args:
        outcome: Per-(series, model) codes, shape (B, M).

    Returns:
        One code per series, shape (B,).
    """
    codes = np.asarray(outcome, dtype=np.uint8)
    any_ok = np.any(codes == Outcome.OK.code, axis=1)
    if codes.shape[1] == 1:
        merged = codes[:, 0]
    else:
        merged = merge_outcomes(*(codes[:, m] for m in range(codes.shape[1])))
    return np.where(any_ok, np.uint8(Outcome.OK.code), merged).astype(np.uint8)


def check_status_invariant(
    outcome: NDArray[np.uint8],
    values: dict[str, NDArray[np.float64]],
    *,
    exempt_when_ok: frozenset[str] = frozenset(),
) -> None:
    """Check the bidirectional status/value invariant on one tile's arrays.

    Args:
        outcome: Per-(series, model) codes, shape (B, M).
        values: Named per-(series, model, ...) float arrays whose leading two
            axes are `(B, M)`. `/selection/` is not among them.
        exempt_when_ok: Names excused from the OK-implies-finite direction. The
            non-OK-implies-NaN direction always applies -- a designed NaN is
            still NaN where the fit failed.

    Raises:
        InvariantError: If a NaN coexists with `OK`, if a non-`OK` cell carries
            any finite value, or if any value is `-inf` -- the finite-looking
            sentinel that survives an `isfinite` check downstream.
    """
    codes = np.asarray(outcome, dtype=np.uint8)
    ok = codes == Outcome.OK.code
    for name, array in sorted(values.items()):
        data = np.asarray(array, dtype=np.float64)
        flat = data.reshape(*codes.shape, -1)
        if np.any(np.isneginf(flat)):
            raise InvariantError(
                f"{name} carries -inf, which is the optimizer's internal barrier "
                "value and a finite-looking sentinel downstream; failed "
                "candidates carry NaN"
            )
        finite = np.isfinite(flat).any(axis=2)
        nan_anywhere = np.isnan(flat).any(axis=2)
        if name not in exempt_when_ok and np.any(ok & nan_anywhere):
            index = np.argwhere(ok & nan_anywhere)[0]
            raise InvariantError(
                f"{name} has a NaN at series {index[0]}, model {index[1]}, whose "
                f"status is OK; a NaN never coexists with OK"
            )
        if np.any(~ok & finite):
            index = np.argwhere(~ok & finite)[0]
            code = Outcome.from_code(int(codes[index[0], index[1]]))
            raise InvariantError(
                f"{name} has a finite value at series {index[0]}, model "
                f"{index[1]}, whose status is {code.value}; a non-OK status has "
                "NaN in all its value slots, or a partially written failure "
                "leaves numbers that read as valid"
            )


def _unpad(padded: NDArray[np.float64], index: RaggedIndex) -> NDArray[np.float64]:
    """Flatten `(B, M, p_max)` NaN-padded parameters onto the ragged axis.

    **THIS IS WHERE 12.3's PADDING AMBIGUITY IS RESOLVED.** In memory a padded
    slot and a failed fit are both NaN and indistinguishable; on the ragged axis
    the padding does not exist, so a NaN there means the fit failed and nothing
    else. Doing it any other way would carry the ambiguity into the store, which
    is the reason 12.3 rejects the padded layout.

    Args:
        padded: Shape (B, M, p_max).
        index: The `/noise/` ragged index.

    Returns:
        Shape (B, P_total).
    """
    source = np.asarray(padded, dtype=np.float64)
    out = np.full((source.shape[0], index.total), np.nan, dtype=np.float64)
    for model, extent in enumerate(index.extents):
        out[:, index.block(model)] = source[:, model, :extent]
    return out


def _array(root: zarr.Group, group: str, name: str) -> zarr.Array[Any]:
    """Return one array of an opened store, narrowed for the type checker."""
    holder = root[group]
    if not isinstance(holder, zarr.Group):  # pragma: no cover - store invariant
        raise TypeError(f"{group} is not a group")
    array = holder[name]
    if not isinstance(array, zarr.Array):  # pragma: no cover - store invariant
        raise TypeError(f"{group}/{name} is not an array")
    return array


def write_tile(
    store_path: Path | str,
    tile: Tile,
    result: FitResult,
    *,
    criteria: Sequence[str],
    index: RaggedIndex,
    has_trend: bool,
) -> None:
    """Write one tile's fits into every group, as one region write per array.

    Args:
        store_path: An existing store.
        tile: The spatial block these results belong to. `result`'s series axis
            is the tile's points in row-major order, which is the order
            `tiling.assemble_tile` produces.
        result: What `fit` returned for that tile.
        criteria: Criterion names in the store's `c` order.
        index: The `/noise/` ragged index for this candidate set.
        has_trend: Whether the design carries a trend column. `n_eff_trend` is
            NaN by design when it does not, and the write path cannot tell that
            from a defect without being told.

    Raises:
        InvariantError: If the status/value invariant fails on the arrays about
            to be written.
        ValueError: If the tile's point count disagrees with the result's series
            axis, or the candidate count with the store's model axis, or the
            criterion list with the store's.
    """
    rows, columns = tile.y_stop - tile.y_start, tile.x_stop - tile.x_start
    batch, models = result.outcome.shape
    if rows * columns != batch:
        raise ValueError(
            f"tile holds {rows * columns} points and the result has {batch} "
            "series; the write path pairs them positionally in row-major order"
        )

    root = zarr.open_group(str(store_path), mode="r+")
    if _array(root, "status", "outcome").shape[2] != models:
        raise ValueError(
            f"the store's model axis is "
            f"{_array(root, 'status', 'outcome').shape[2]} long and the result "
            f"has {models} candidates"
        )
    stored_criteria = [
        str(name) for name in np.asarray(_array(root, "selection", "c")[:]).tolist()
    ]
    if stored_criteria != list(criteria):
        raise ValueError(
            f"the store's criterion axis is {stored_criteria} and the write was "
            f"given {list(criteria)}; the c axis is positional"
        )

    theta = _unpad(result.theta, index)
    theta_err = _unpad(result.theta_err, index)
    unconstrained = _unpad(result.theta_unconstrained, index)

    check_status_invariant(
        result.outcome,
        {
            "beta": result.beta,
            "beta_err": result.beta_err,
            "log_lik": result.loglik,
            "k": result.scores.k,
            "n": result.scores.n,
            "n_eff_bic": result.n_eff_bic,
            "n_eff_trend": result.n_eff_trend,
        },
        exempt_when_ok=frozenset() if has_trend else frozenset({"n_eff_trend"}),
    )

    region = (slice(tile.y_start, tile.y_stop), slice(tile.x_start, tile.x_stop))

    def put(group: str, name: str, values: NDArray[Any], *shape: int) -> None:
        _array(root, group, name)[region] = np.asarray(values).reshape(
            rows, columns, *shape
        )

    put("signal", "beta", result.beta, models, result.beta.shape[-1])
    put("signal", "beta_err", result.beta_err, models, result.beta_err.shape[-1])
    put("primitives", "log_lik", result.loglik, models)
    put("primitives", "k", result.scores.k, models)
    put("primitives", "n", result.scores.n, models)
    put("primitives", "n_eff_bic", result.n_eff_bic, models)
    put("primitives", "n_eff_trend", result.n_eff_trend, models)
    put("primitives", "iterations", result.n_iter.astype(np.uint16), models)
    put("noise", "theta", theta, index.total)
    put("noise", "theta_err", theta_err, index.total)
    put("warmstart", "theta_unconstrained", unconstrained, index.total)
    put("status", "outcome", result.outcome, models)
    put("status", "point_outcome", point_outcomes(result.outcome))

    _write_selection(root, region, result, criteria, rows, columns, models)


def _write_selection(
    root: zarr.Group,
    region: tuple[slice, slice],
    result: FitResult,
    criteria: Sequence[str],
    rows: int,
    columns: int,
    models: int,
) -> None:
    """Rank the same fits under every criterion and write `/selection/`.

    **ONE `CandidateScores`, C RANKINGS, NO REFIT.** This is design doc 12.8's
    claim exercised at the point it is produced rather than only at the recompute
    path: the criteria are arithmetic over primitives, so a second criterion
    costs a ranking and never a fit.

    Args:
        root: The opened store.
        region: The tile's `(y, x)` slices.
        result: What `fit` returned.
        criteria: Criterion names in the store's `c` order.
        rows: Tile rows.
        columns: Tile columns.
        models: Model axis length.

    Raises:
        ValueError: If two criteria disagree about `n_valid`, which counts
            **fits** and is criterion-independent by construction -- so a
            disagreement means one of them is counting something else.
    """
    shape_mc = (rows, columns, models, len(criteria))
    delta = np.empty(shape_mc, dtype=np.float64)
    weight = np.empty(shape_mc, dtype=np.float64)
    ic_best = np.empty((rows, columns, len(criteria)), dtype=np.float64)
    selected = np.empty((rows, columns, len(criteria)), dtype=np.int16)
    n_valid: NDArray[np.int64] | None = None

    for position, name in enumerate(criteria):
        ranking = rank_candidates(result.scores, Criterion(name))
        delta[..., position] = ranking.delta_ic.reshape(rows, columns, models)
        weight[..., position] = ranking.weights.reshape(rows, columns, models)
        ic_best[..., position] = ranking.ic_best.reshape(rows, columns)
        selected[..., position] = ranking.best_index.reshape(rows, columns)
        if n_valid is None:
            n_valid = ranking.n_valid
        elif not np.array_equal(n_valid, ranking.n_valid):
            raise ValueError(
                f"criterion {name!r} reports a different n_valid than the first "
                "criterion; n_valid counts fits and is criterion-independent"
            )

    assert n_valid is not None  # noqa: S101 - criteria is non-empty by schema
    _array(root, "selection", "delta_ic")[region] = delta
    _array(root, "selection", "weight")[region] = weight
    _array(root, "selection", "ic_best")[region] = ic_best
    _array(root, "selection", "selected")[region] = selected
    _array(root, "selection", "n_valid")[region] = n_valid.reshape(
        rows, columns
    ).astype(np.int16)

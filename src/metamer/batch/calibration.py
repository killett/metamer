"""The calibration cache: a measured slope, reused where it is still true.

**ONLY THE SLOPE IS CACHED.** The floor is measured fresh every run and
deliberately never cached (`memory.measure_floor`), because keying it would need
the input's chunk grid -- which Phase 2a Task 11's (a1) sweep classified as read
back from the store rather than hashed. **An uncached quantity has no staleness
failure mode**, and that is the whole reason the two are treated differently.

**THE STORE NEVER RESOLVES THROUGH THE CACHE.** The cache is an input to store
creation and nothing reads it afterwards -- a resume reads the tile side back out
of the store (a1). Deleting the cache never makes a store unreadable, incomplete
or unopenable; it costs a re-measurement.

    **AND THE PRECISE FORM OF THAT CLAIM MATTERS.** Where the calibrated side
    was LARGER than the analytic one -- which happens when the measured slope
    comes in below the formula -- a later resume that cannot reach the cache
    derives a smaller side and is refused by `completion.resume_tile_side`'s
    *stored > derived* arm. The store is intact; the resume needs the cache or a
    larger budget. Naming that refusal is Phase 2b Task 6's job, and the claim
    is written here in the narrow form rather than the brief's broader one.

**NO EXPIRY, AND NOT EVEN AS A BACKSTOP** (design doc 11.4, amended 2026-08-15).
Time does not cause the change it stands in for -- that is (a2) at a cache key, a
gate made of a name for the real condition. A backstop firing on a schedule
unrelated to the hazard re-measures when nothing changed and stays silent when
something did, **and its presence makes the real gate look optional.** The real
gates are the machine fingerprint and a digest over every installed
distribution; `--recalibrate` is the manual override and it is honest, because it
fires exactly when a human has reason to believe the measurement is stale.
"""

from __future__ import annotations

import json
import os
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from metamer.core import hashing
from metamer.core.memory import (
    CalibrationPoint,
    CalibrationResult,
    MemoryEngineLabel,
    SolverPlacement,
    slope_band,
)

CACHE_SUFFIX = ".calibration.json"
"""Appended to the store's name to get its cache's name.

**A SIBLING IN THE STORE'S PREFIX, NEVER A MEMBER OF THE GROUP.** Design doc
11.4 and 15.5 require the cache to live with the store rather than in local
scratch -- anything in local temp is gone when a preemptible instance restarts --
and 12.4 requires every store to be self-contained. Both hold because the store
never resolves through the cache.

**Inside the store's root attrs would be self-contained and useless**: a fresh
store has no attrs yet, so the cache would only ever serve resumes, and a resume
already reads its side back out of the store. **Inside the store DIRECTORY would
break two things**: Phase 2a's exit criterion 1 walks a store byte for byte, so
two runs of one configuration would stop being byte-identical, and the file would
appear as an unrecognized member of the zarr group.
"""

CACHE_FORMAT = 1
"""On-disk layout version for the cache file itself.

Recorded so an incompatible future layout is a **miss** rather than a
misinterpretation. It is not `store.SCHEMA_VERSION`: a cache is disposable by
construction, so the response to an unrecognized layout is to re-measure, which
is the response to every other unreadable cache here.
"""


def cache_path(store_path: Path | str) -> Path:
    """Return the cache that belongs to a store.

    Args:
        store_path: Where the store is, or will be.

    Returns:
        A path in the store's own prefix, outside the store itself.
    """
    store = Path(store_path)
    return store.with_name(store.name + CACHE_SUFFIX)


def _pairs(
    versions: Mapping[str, str] | Iterable[tuple[str, str]],
) -> list[tuple[str, str]]:
    """Return `(name, version)` pairs, sorted and deduplicated.

    Args:
        versions: A mapping, or any iterable of pairs.

    Returns:
        The pairs, sorted.
    """
    items = versions.items() if isinstance(versions, Mapping) else versions
    return sorted({(str(name), str(version)) for name, version in items})


def _grouped(pairs: Iterable[tuple[str, str]]) -> dict[str, str]:
    """Collapse sorted pairs to one entry per name, joining duplicates.

    **`dict(pairs)` KEEPS THE LAST OF A DUPLICATED KEY, WHICH IS THE DEFECT.**
    An installed distribution shadowed by a source tree on the path reports two
    versions of one name, and silently keeping either makes an ambiguous
    environment digest as an unambiguous one -- so the digest stops moving when
    the shadowed copy changes. The rule is stated here rather than inherited
    from the container.

    Args:
        pairs: Sorted `(name, version)` pairs.

    Returns:
        One entry per name; duplicated names carry every version, joined.
    """
    grouped: dict[str, list[str]] = {}
    for name, version in pairs:
        grouped.setdefault(name, []).append(version)
    return {name: ",".join(versions) for name, versions in grouped.items()}


def installed_versions() -> dict[str, str]:
    """Return every installed distribution's version, plus metamer's own.

    **READ FROM THE ENVIRONMENT, NEVER FROM THE DECLARATION.** `pixi.toml`'s
    ranges would give one digest across every version they permit, which is the
    whole hazard; and a curated list has the `cftime` hole by construction --
    2a Task 2 established that a dependency reached **through** another library
    is invisible to any static import scan.

    **AND metamer ITSELF IS ADDED, BECAUSE IT IS THE ONE DISTRIBUTION THIS
    INSTRUMENT CANNOT SEE HERE.** Measured 2026-08-15: in a source-layout tree
    `importlib.metadata` reports no `metamer` distribution at all, so *"every
    installed distribution, excluding nothing"* taken literally excludes exactly
    the package whose memory behaviour the slope describes -- the fill-value
    shape at a digest, where "metamer did not change" and "metamer is invisible
    to this instrument" produce the identical value. Where both readings exist
    they are joined rather than resolved, by `_grouped`'s rule.

    Returns:
        Distribution name to version. Sorted by construction.
    """
    import importlib.metadata

    import metamer

    pairs = [
        (distribution.name or "<unnamed>", distribution.version or "<unknown>")
        for distribution in importlib.metadata.distributions()
    ]
    pairs.append(("metamer", metamer.__version__))
    return _grouped(_pairs(pairs))


def versions_digest(
    versions: Mapping[str, str] | Iterable[tuple[str, str]] | None = None,
) -> tuple[str, dict[str, str]]:
    """Return a digest over installed versions, and the versions it covers.

    **THE CONTRIBUTORS COME BACK BESIDE THE ROLLUP**, on `geometry_hash`'s
    precedent: a digest that has moved says only that something changed, and the
    thing a user needs is the name of the package that moved.

    **SORTED BEFORE HASHING, WHICH IS (k).** `importlib.metadata.distributions`
    yields in `sys.path` and directory order, so a digest taken over that order
    is stable within one process and unstable between them -- invisible to every
    same-process test and to mutation testing, and fatal for an artifact whose
    only purpose is to be read by a later process.

    Args:
        versions: What to digest. Reads the environment when omitted; a mapping
            or an iterable of pairs otherwise, which is the seam that lets the
            "a moved version moves the digest" claim be tested from two
            constructed environments rather than from this one.

    Returns:
        The 16-hex-digit digest, and the name-to-version mapping behind it.
    """
    grouped = installed_versions() if versions is None else _grouped(_pairs(versions))
    return hashing.digest({"versions": grouped}), grouped


def cache_key(
    *,
    fit_hash: str,
    placement: str,
    engine_label: str,
    machine: str,
    versions: str,
) -> str:
    """Return the key an entry is filed under.

    **THE FIVE COMPONENTS, AND WHY EACH IS ONE** (design doc 11.4, as amended):

    - `fit_hash` -- the dataset, the candidate set and the objective. The
      regressor regime rides inside it **by construction**, because it lives in
      `signal_terms`, which is fit-relevant; a sibling config field would have
      let a cached shared-X measurement serve a per-point run and understate
      peak by 3.3x.
    - `placement` -- one value is reachable today and it is in the key anyway,
      on `shared_with`'s precedent: the day a batched driver lands, the engine's
      workspace becomes a per-series term, and a key that could not tell the two
      apart would serve the old slope to the new driver.
    - `engine_label` -- **`memory.MemoryEngineLabel`, never `EngineId`.** Both
      shipped engines share `EngineId.KALMAN` deliberately so their scores stay
      rankable; a key built on it would serve one engine's slope to the other.
    - `machine` -- `(CPU model, physical cores, total RAM)` hashed, read from
      the platform by `machine.fingerprint`. **This is the field whose
      classification changes with its consumer**: harmless self-reported
      provenance while it reached `run_hash` alone, and an identity the moment
      this key reads it.
    - `versions` -- `versions_digest`'s rollup.

    **The iteration cap is deliberately absent.** Every calibration runs at
    `max_iter = 1` today, so two measurements at different caps cannot collide;
    the result records its own cap, so the collision is diagnosable the day a
    second one exists. A guard over a one-element set would be untestable.

    Args:
        fit_hash: The run's fit identity.
        placement: A `memory.SolverPlacement` value.
        engine_label: A `memory.MemoryEngineLabel` value.
        machine: `machine.fingerprint()`.
        versions: `versions_digest()`'s first element.

    Returns:
        The 16-hex-digit key.
    """
    return hashing.digest(
        {
            "engine_label": engine_label,
            "fit_hash": fit_hash,
            "machine": machine,
            "placement": placement,
            "versions": versions,
        }
    )


def result_payload(result: CalibrationResult) -> dict[str, Any]:
    """Render a `CalibrationResult` to JSON-safe data.

    **EVERY FIELD, NOT JUST THE SLOPE.** A cache entry has to say what the
    number is licensed for, or a later reader cannot tell a slope measured at a
    cap of 1 over four tiny tiles from one measured at production sizes.
    `linearity_basis` is the field a "just the number" cache drops, and it is
    the one that says the slope is not licensed beyond its ladder.

    Args:
        result: What `memory.calibrate` returned.

    Returns:
        The payload.
    """
    return {
        "slope_bytes_per_series": float(result.slope_bytes_per_series),
        "intercept_bytes": float(result.intercept_bytes),
        "residuals": [float(value) for value in result.residuals],
        "points": [
            {
                "side": point.side,
                "derived_side": point.derived_side,
                "batch": point.batch,
                "peak_bytes": float(point.peak_bytes),
                "baseline_bytes": float(point.baseline_bytes),
                "ok": point.ok,
                "attempted": point.attempted,
            }
            for point in result.points
        ],
        "max_iter": int(result.max_iter),
        "linearity_basis": result.linearity_basis,
        "placement": str(result.placement),
        "engine_label": str(result.engine_label),
        "floor_peak_bytes": int(result.floor_peak_bytes),
    }


def result_from_payload(payload: Mapping[str, Any]) -> CalibrationResult:
    """Rebuild a `CalibrationResult` from `result_payload`'s output.

    Args:
        payload: A rendered result.

    Returns:
        The result.

    Raises:
        KeyError: If a field is absent. **Refused rather than defaulted**: a
            missing `placement` or `engine_label` defaulted to the reachable
            value would file an unmeasured shape under a measured one's key,
            which is the one failure a cache cannot detect.
        ValueError: If a placement or engine label is not one this version
            knows, for the same reason.
    """
    return CalibrationResult(
        slope_bytes_per_series=float(payload["slope_bytes_per_series"]),
        intercept_bytes=float(payload["intercept_bytes"]),
        residuals=tuple(float(value) for value in payload["residuals"]),
        points=tuple(
            CalibrationPoint(
                side=int(point["side"]),
                derived_side=int(point["derived_side"]),
                batch=int(point["batch"]),
                peak_bytes=float(point["peak_bytes"]),
                baseline_bytes=float(point["baseline_bytes"]),
                ok=int(point["ok"]),
                attempted=int(point["attempted"]),
            )
            for point in payload["points"]
        ),
        max_iter=int(payload["max_iter"]),
        linearity_basis=str(payload["linearity_basis"]),
        placement=SolverPlacement(payload["placement"]),
        engine_label=MemoryEngineLabel(payload["engine_label"]),
        floor_peak_bytes=int(payload["floor_peak_bytes"]),
    )


def _read(path: Path) -> dict[str, Any]:
    """Return the cache file's entries, or an empty mapping.

    **AN UNREADABLE CACHE IS A MISS AND NEVER AN ERROR.** The cache lives beside
    the store on a preemptible instance (15.5), so a half-written file is a state
    that occurs; re-measuring is the safe direction, and refusing to run because
    a *cache* is damaged would fail exactly the resume the arrangement exists to
    serve.

    Args:
        path: The cache file.

    Returns:
        Key to entry, empty if the file is absent, unparseable, or written under
        a layout this version does not know.
    """
    try:
        payload = json.loads(path.read_text())
    except (OSError, ValueError):
        return {}
    if not isinstance(payload, Mapping) or payload.get("format") != CACHE_FORMAT:
        return {}
    entries = payload.get("entries")
    return dict(entries) if isinstance(entries, Mapping) else {}


def load(path: Path | str, key: str) -> CalibrationResult | None:
    """Return the entry filed under `key`, or None.

    **UNDER `key` AND NEVER "the one that is there".** A cache holding a
    calibration is not a cache holding a calibration *for this*, and serving the
    only entry present is the `observed`-recorded-and-ignored shape 2a Task 5
    already found once -- here it would size a tile from a slope measured under
    different code, against a constraint the design doc calls hard.

    Args:
        path: The cache file.
        key: What `cache_key` returned.

    Returns:
        The cached result, or None if this cache has nothing under that key.
    """
    entry = _read(Path(path)).get(key)
    if not isinstance(entry, Mapping):
        return None
    try:
        return result_from_payload(entry["result"])
    except (KeyError, TypeError, ValueError):
        # A malformed ENTRY is a miss for the same reason a malformed FILE is:
        # the only thing lost is a measurement, and the alternative is a run
        # that fails because something disposable was damaged.
        return None


def store(
    path: Path | str,
    key: str,
    result: CalibrationResult,
    *,
    versions: Mapping[str, str],
) -> None:
    """File `result` under `key`, keeping whatever else the cache holds.

    **MERGED, NEVER REPLACED.** The key exists so heterogeneous nodes each get
    their own entry automatically (11.4); a cache that held one entry would make
    two nodes alternating over one store re-measure on every alternation, which
    is invisible except as a bill.

    **THE CONTRIBUTING VERSIONS GO IN THE ENTRY, NOT ONLY THEIR DIGEST**, on
    `geometry_hash`'s precedent: a key that no longer matches says only that
    something moved, and the entry's own version map is what names the package.

    **WRITTEN THROUGH A TEMPORARY AND `os.replace`**, so an interrupted write
    leaves the previous cache rather than a truncated one -- the same
    preemption that motivates the cache is what would truncate it. An
    unparseable existing file is replaced wholesale: the entries that would be
    preserved are unreadable anyway.

    Args:
        path: The cache file.
        key: What `cache_key` returned.
        result: The measurement.
        versions: `versions_digest()`'s second element, the map behind the
            digest in `key`.

    Raises:
        OSError: If the cache cannot be written. **Not swallowed**: a read
            failure costs a re-measurement, and a write failure that looked
            successful would cost one on every future run with no symptom.
    """
    destination = Path(path)
    digest, grouped = versions_digest(versions)
    entries = _read(destination)
    entries[key] = {
        "key": key,
        "versions_digest": digest,
        "versions": grouped,
        "result": result_payload(result),
    }
    temporary = destination.with_name(destination.name + ".tmp")
    temporary.write_text(
        json.dumps({"format": CACHE_FORMAT, "entries": entries}, sort_keys=True)
    )
    os.replace(temporary, destination)


def unusable_reason(result: CalibrationResult, *, analytic: float) -> str | None:
    """Say why a measured slope must not size a tile, or None if it may.

    **THE RULE IS THE DESIGN DOC's OWN.** Section 11.4 requires the calibration
    to be *validated against section 9.4's analytic formula*, and
    `memory.slope_band` is that validation -- the two-sided 1.5x band Task 4's
    ladder passed for the first time against the production path.

    **TWO FAILURE MODES MAKE IT NECESSARY RATHER THAN TIDY.** A **non-positive**
    slope makes `memory.tile_side` take the square root of a negative, so the
    symptom is a traceback out of arithmetic rather than a diagnosis; Task 4
    measured +-0.3 MB of scatter between fresh children against 0.43 MB of
    signal at small sides, and its published ladder's first two peaks *decrease*
    with B. A **small positive** slope raises nothing at all and sizes an
    enormous tile: 5 B/series is a plausible number and the arithmetic does not
    object to it. The band's lower bound is positive, so one rule covers both.

    **THE CALLER FALLS BACK RATHER THAN REFUSING, AND THAT IS A DECISION.** A
    refusal after a multi-hour measurement, on a criterion the user cannot
    influence, converts a usable-but-conservative outcome into no outcome -- and
    the fallback target is exactly what the same run does without `--calibrate`,
    so nothing is degraded relative to every run shipped so far. It is also what
    makes the reachability pair testable: under a refusal, a suite-affordable
    calibration fails on the sign of a noise-dominated slope, and *"--calibrate
    produces an entry"* could not be asserted deterministically.

    **THE COST OF THE BAND, STATED:** a calibration can move the per-series cost
    by at most 1.5x and therefore the tile side by at most sqrt(1.5) = 1.22x. A
    genuine disagreement larger than that is a finding about the formula, which
    is Phase 2b Task 7's subject, and it reaches the user as this string.

    Args:
        result: The measurement.
        analytic: What `memory.resident_bytes_per_series` predicts for this
            run's geometry.

    Returns:
        None if the slope may size a tile; otherwise a sentence naming both
        numbers, the band and what the run did instead.
    """
    low, high = slope_band(analytic)
    slope = result.slope_bytes_per_series
    if low <= slope <= high:
        return None
    return (
        f"the calibration measured {slope:g} B/series against the formula's "
        f"{analytic:g}, which is outside the {low:.4g}-{high:.4g} B/series band "
        f"design doc section 11.4 validates a calibration against, so the tile "
        f"was sized by the formula instead and the measurement was recorded "
        f"rather than used. A disagreement this large is a finding about the "
        f"formula rather than a tile size; --recalibrate measures again, and "
        f"the ladder this one used was: {result.linearity_basis}"
    )


def provenance(
    *,
    key: str,
    result: CalibrationResult,
    digest: str,
    versions: Mapping[str, str],
    rejected: str | None,
) -> dict[str, Any]:
    """Build the store's record of a calibration it consulted.

    **WRITTEN WHENEVER A CALIBRATION WAS CONSULTED, USED OR NOT.** Under
    `unusable_reason`'s fallback a rejected measurement leaves
    `tile_side_basis` at `default`, which is also what a run that never
    calibrated writes -- so without this block a store that spent 26.5 h
    measuring is indistinguishable from one that measured nothing. **The absence
    of this key is what means "no calibration was consulted"**, on the
    `source_*` precedent, and `rejected` is what says why the measurement did
    not produce the side.

    Args:
        key: The cache key this run computed.
        result: The measurement, cached or measured this session.
        digest: The versions digest inside `key`.
        versions: The map behind the digest, so a later mismatch names the
            package that moved.
        rejected: `unusable_reason`'s answer.

    Returns:
        A JSON-safe mapping for the store's root attrs.
    """
    payload = result_payload(result)
    payload.update(
        {
            "key": key,
            "versions_digest": digest,
            "versions": dict(versions),
            "rejected": rejected,
        }
    )
    return payload

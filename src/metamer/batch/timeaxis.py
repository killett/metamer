"""The time axis: decoded timestamps in, decimal years out.

**metamer converts to decimal years. The user never supplies them.** Phase 1
measured what an interface that asks for them invites: the same 20-year monthly
design on a seconds-since-1970 axis goes from `cond(X) = 3.4e1` to `3.3e32` and
from rank 7/7 to 2/7, `cos(annual)` becomes identically 1.0, and the design
looks full rank while having silently lost five columns. **An interface that
cannot be used wrongly beats a validator that catches it.**

**THE CONVENTION, WHICH THE DESIGN DOC REQUIRED AND DID NOT STATE.** §13.6 says
the conversion is fit identity and that three calendars give different answers,
but no document said what the formula is -- and two reasonable formulas differ
enough to matter. It is fixed here, in one place, under `ALGORITHM_VERSION`:

    decimal_year(t) = year(t) + (t - start_of_year) / (start_of_next_year - start_of_year)

i.e. **the fraction of the actual year `t` falls in**, evaluated in `t`'s own
calendar. A calendar year is exactly 1.0 in every calendar.

The alternative -- `epoch_year + elapsed_seconds / (365.25 * 86400)` -- was
rejected on a measurement, not a preference. The design matrix carries `Annual`
and `SemiAnnual` harmonics, so a formula under which a calendar year is not
exactly 1.0 makes those columns drift against the seasons they model:

| calendar | year length | drift of `/365.25` per year | over 50 years |
|---|---|---|---|
| `proleptic_gregorian` | 365 or 366 d | up to 0.75 d | ~0.5 d, bounded (leap cycle re-syncs) |
| `noleap` | 365 d | 0.25 d | 12.5 d |
| `360_day` | 360 d | **5.25 d (1.46%)** | **0.72 YEARS -- the harmonic is decorrelated** |

The `360_day` row is decisive: that is not a small phase error, it is a
different signal. `360_day` is an ordinary climate-model calendar, so this is a
reachable input rather than a hypothetical.

**The cost of the chosen convention, stated because it is not free.** Because a
year is exactly 1.0, a daily axis has TWO distinct timesteps in a Gregorian
calendar (1/365 and 1/366) where `/365.25` has one, so `StateSpace.unique_dt`
returns 2 and `F`/`Q` are built twice per series per iteration instead of once.
Measured on 20 years of daily data. That is the whole of the cost and it buys
harmonics that do not drift.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Sequence
from typing import Any, Protocol

import numpy as np
from numpy.typing import NDArray


class CalendarDate(Protocol):
    """What both `datetime.datetime` and a `cftime` date provide.

    The conversion needs exactly three things: the year, a `replace` that
    preserves the calendar, and a subtraction yielding something with
    `total_seconds`. Both types satisfy all three, which is why one formula
    covers every calendar without branching on a calendar name.

    Typed as a protocol rather than `Any` so the structural requirement is
    stated where a reader looks: a date type missing `replace` is the defect
    `_start_of_year` documents, and `Any` would let it through silently.
    """

    year: int

    def replace(self, **kwargs: int) -> CalendarDate:
        """Return a copy with the given fields replaced, same calendar."""
        ...

    def __sub__(self, other: CalendarDate) -> dt.timedelta:
        """Return the interval to `other`."""
        ...


def _start_of_year(sample: CalendarDate, year: int) -> CalendarDate:
    """Return 1 January of `year` in `sample`'s own calendar.

    **`.replace()`, NOT `type(sample)(year, 1, 1)`, AND THE DIFFERENCE IS THE
    WHOLE POINT OF THIS FUNCTION.** `cftime.datetime` carries its calendar as an
    *attribute*, not as a subclass: `cftime.datetime(2000, 1, 1,
    calendar="noleap")` is a `cftime.datetime`, so reconstructing through
    `type(sample)` produces a date on the DEFAULT calendar. The denominator would
    then be a standard year's length while the numerator was measured in a
    `noleap` or `360_day` one -- a silently wrong conversion, on exactly the
    calendars the conversion exists to handle. Caught by
    `test_a_calendar_year_is_exactly_one_in_every_calendar`, which is the test
    written for it.

    `.replace()` preserves the calendar and is spelled the same way on
    `datetime.datetime`, so one formula still covers every calendar without
    branching on a calendar name.

    Args:
        sample: A date whose calendar is to be preserved.
        year: The year to construct.

    Returns:
        The start of `year`, on `sample`'s calendar.
    """
    return sample.replace(
        year=year, month=1, day=1, hour=0, minute=0, second=0, microsecond=0
    )


def to_decimal_years(values: Sequence[Any] | NDArray[Any]) -> NDArray[np.float64]:
    """Convert decoded timestamps to decimal years.

    Args:
        values: Decoded timestamps -- `numpy.datetime64`, `datetime.datetime`,
            or `cftime` dates. **Never raw numbers**: a bare numeric axis has no
            calendar and no epoch, and inferring either is the error this whole
            module exists to prevent.

    Returns:
        Decimal years, shape `(n,)`, float64.

    Raises:
        TypeError: If `values` is a numeric array. The message says what is
            required, because "cannot convert" without naming the fix is a wall.
    """
    array = np.asarray(values)
    if array.dtype.kind in "iuf":
        raise TypeError(
            "the time axis is numeric, so it carries no calendar and no epoch. "
            "Decode it to datetime64 or cftime dates first -- metamer converts "
            "to decimal years and never infers a unit from magnitude"
        )
    if array.dtype.kind == "M":
        # datetime64 -> datetime.datetime. Microseconds, not nanoseconds:
        # `.astype(object)` on datetime64[ns] yields plain ints, silently, and
        # the resulting "years" would be ~1e18.
        array = array.astype("datetime64[us]").astype(object)

    out = np.empty(array.shape, dtype=np.float64)
    flat = array.ravel()
    result = out.ravel()
    for index, stamp in enumerate(flat):
        year = stamp.year
        start = _start_of_year(stamp, year)
        end = _start_of_year(stamp, year + 1)
        elapsed = (stamp - start).total_seconds()
        length = (end - start).total_seconds()
        result[index] = year + elapsed / length
    return out


def check_strictly_increasing(t: NDArray[np.float64]) -> None:
    """Refuse a time axis that is not strictly increasing.

    **STRICTLY, NOT MERELY MONOTONICALLY**, which catches three faults in one
    comparison: a reversal, a duplicate, and a single-sample axis.

    The duplicate is the one worth spelling out. Two observations sharing a
    timestamp give `dt = 0`, which in continuous time is an identity transition
    with a **zero process-noise covariance** -- singular. It would surface deep
    inside the filter as a failed Cholesky or a fabricated innovation variance,
    rather than at the boundary where the input can still be named. Duplicate
    timestamps are ordinary in real records; the Matern nu=1/2 `Delta t = 0`
    case exists precisely because of them.

    Args:
        t: Decimal years, shape `(n,)`.

    Raises:
        ValueError: If `t` has fewer than two entries, or any step is
            non-positive. The message names the index and both values, since
            "not increasing" alone does not locate the fault in 10^7 series.
    """
    if t.size < 2:
        raise ValueError(
            f"the time axis has {t.size} sample(s); a fit needs at least two, "
            "and a single-sample axis has no timestep at all"
        )
    steps = np.diff(t)
    bad = np.flatnonzero(steps <= 0.0)
    if bad.size:
        first = int(bad[0])
        kind = "duplicate" if steps[first] == 0.0 else "decreasing"
        raise ValueError(
            f"the time axis is not strictly increasing: {kind} at index "
            f"{first + 1}, t[{first}] = {t[first]!r} and t[{first + 1}] = "
            f"{t[first + 1]!r}. A duplicate timestamp gives an identity "
            "transition with zero process noise, which is singular"
        )


def unique_dt_count(t: NDArray[np.float64]) -> int:
    """Count the distinct timesteps of a time axis.

    **`StateSpace.unique_dt` IS REUSED, NOT RE-ROLLED.** It is the function that
    actually decides how many times `F` and `Q` are built per series per
    optimizer iteration, and it is tolerance-aware in a specific way -- a local,
    per-pair relative tolerance rather than a global one. A second implementation
    here would report a number that no longer describes the cost it exists to
    describe.

    **WHAT THIS NUMBER IS, MEASURED, BECAUSE THE OBVIOUS READING IS WRONG.** A
    "regular" axis does not generally give 1:

    | axis | unique steps |
    |---|---|
    | 50 years of month-start timestamps | **6** |
    | the same, mid-month | **8** |
    | 20 years of daily timestamps | **2** (1/365 and 1/366) |
    | a synthetic `2000 + arange(n)/12` axis | 1 |

    Calendar months are 28-31 days, so real monthly data is genuinely irregular
    and the amortization does not apply to it. **The synthetic axis is the only
    one that gives 1**, which matters because that is what benchmarks are built
    from -- see the open question in `PROGRESS.md`.

    **AND THE HAZARD THIS REPORTS IS NOT FLOAT NOISE.** Measured against
    `UNIQUE_DT_RTOL = 1e-9`: a monthly axis perturbed at 1e-16 of its value --
    i.e. float64 rounding from the conversion itself -- still collapses to the
    same count, because the tolerance is far above it. What breaks the collapse
    is **real sub-second jitter**: on a monthly axis the per-pair tolerance is
    about 2.6 ms, and timestamps scattered by more than that report one distinct
    step per sample. That is a genuine property of some records, and it costs an
    order of magnitude with nothing else saying why -- which is why it is
    recorded in provenance.

    **Do NOT respond to a large count by lowering `UNIQUE_DT_RTOL`.** It would
    destroy the amortization on every axis, to hide a number that is telling the
    truth about this one.

    Args:
        t: Decimal years, shape `(n,)`.

    Returns:
        The number of distinct timesteps.
    """
    from metamer.core.statespace import StateSpace

    return int(StateSpace.unique_dt(t).size)


def calendar_of(values: Sequence[Any] | NDArray[Any]) -> str:
    """Return the calendar name of decoded timestamps.

    **THE DECODED CALENDAR, NEVER THE ATTRS STRING.** Reading `units`/`calendar`
    out of the file's attributes would make the fingerprint inherit xarray's and
    cftime's parsing behaviour, so a dependency upgrade that changed how an
    unusual spelling decodes would silently invalidate every store. Asking the
    decoded object what it is asks the thing that actually produced the numbers.

    Args:
        values: Decoded timestamps.

    Returns:
        The CF calendar name.

    Raises:
        TypeError: If the values are not decoded timestamps.
    """
    array = np.asarray(values)
    if array.dtype.kind == "M":
        return "proleptic_gregorian"
    if array.size == 0:
        raise TypeError("cannot determine the calendar of an empty time axis")
    sample = array.ravel()[0]
    calendar = getattr(sample, "calendar", None)
    if calendar is not None:
        return str(calendar)
    if isinstance(sample, dt.datetime):
        return "proleptic_gregorian"
    raise TypeError(
        f"time values of type {type(sample).__name__} are not decoded "
        "timestamps; expected datetime64, datetime, or a cftime date"
    )

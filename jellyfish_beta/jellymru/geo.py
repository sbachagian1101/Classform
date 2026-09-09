"""Bearing arithmetic and onshore-component helpers.

Conventions
-----------
* Bearings are compass degrees: 0 = north, 90 = east, clockwise.
* ``facing_deg`` for a beach is the shore-normal bearing pointing out to sea.
* Wind and wave directions are *meteorological*: the direction they come FROM.
* Ocean current directions are *oceanographic*: the direction they flow TO.
"""
from __future__ import annotations

import numpy as np


def angular_difference(a, b):
    """Signed smallest difference a - b in degrees, in (-180, 180]."""
    d = (np.asarray(a, dtype=float) - np.asarray(b, dtype=float) + 180.0) % 360.0 - 180.0
    return d


def onshore_component(magnitude, direction_deg, facing_deg, convention: str = "from"):
    """Project a vector quantity onto the shore-normal.

    Positive means the quantity is directed from the sea onto the beach.

    Parameters
    ----------
    magnitude : array-like
        Speed (m/s) or height (m).
    direction_deg : array-like
        Direction in compass degrees.
    facing_deg : float or array-like
        Beach shore-normal bearing pointing out to sea.
    convention : {"from", "to"}
        "from" for wind and waves (direction they arrive from),
        "to" for currents (direction they flow toward).
    """
    mag = np.asarray(magnitude, dtype=float)
    direction = np.asarray(direction_deg, dtype=float)
    if convention == "to":
        direction = (direction + 180.0) % 360.0
    elif convention != "from":
        raise ValueError("convention must be 'from' or 'to'")
    return mag * np.cos(np.radians(angular_difference(direction, facing_deg)))


def signed_square(x):
    """sign(x) * x**2, a wind-stress proxy that keeps onshore/offshore sign."""
    x = np.asarray(x, dtype=float)
    return np.sign(x) * x * x

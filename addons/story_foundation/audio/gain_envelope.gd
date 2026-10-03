# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Derek Wang
extends RefCounted
## Stateless smoothstep gain interpolation; the consumer owns time and lifecycle.

## Finite inputs are required. Nonpositive duration completes immediately.
## Gain endpoints are deliberately not clamped: use linear gain or decibels as needed.
static func sample(from_gain: float, target_gain: float, elapsed: float, duration: float) -> float:
    if duration <= 0.0: return target_gain
    var t := clampf(elapsed / duration, 0.0, 1.0)
    var weight := t * t * (3.0 - 2.0 * t)
    return lerpf(from_gain, target_gain, weight)

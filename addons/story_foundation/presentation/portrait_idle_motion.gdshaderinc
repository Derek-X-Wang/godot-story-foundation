// SPDX-License-Identifier: MIT
// Copyright (c) 2026 Derek Wang
// Stateless mirror of portrait_idle_motion.gd::deform_point; caller-local units.
// Consumers own timing, rest geometry, masks, pins, amplitudes and visual approval.
#ifndef STORY_FOUNDATION_PORTRAIT_IDLE_MOTION
#define STORY_FOUNDATION_PORTRAIT_IDLE_MOTION
bool sf_idle_invalid(vec2 value) {
    return any(isnan(value)) || any(isinf(value));
}
vec2 sf_idle_deform_point(vec2 rest, float inhale, vec2 displacement,
        vec2 pivot, float angle_radians, vec2 weights, bool pinned) {
    if (pinned || sf_idle_invalid(rest) || isnan(inhale) || isinf(inhale)
            || sf_idle_invalid(displacement) || sf_idle_invalid(pivot)
            || isnan(angle_radians) || isinf(angle_radians) || sf_idle_invalid(weights)) {
        return rest;
    }
    float phase = clamp(inhale, 0.0, 1.0);
    vec2 influence = clamp(weights, vec2(0.0), vec2(1.0));
    vec2 arm = rest - pivot;
    float angle = angle_radians * phase;
    float c = cos(angle);
    float s = sin(angle);
    vec2 rotated = vec2(c * arm.x - s * arm.y, s * arm.x + c * arm.y);
    return rest + phase * influence.x * displacement + influence.y * (rotated - arm);
}
#endif

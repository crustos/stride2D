"""scenery.py: backdrops for a level, drawn by the viewport behind the tiles (a project's `backdrop` names one). No images: bands, discs and boxes of the 2D renderer, moved
at different speeds against the camera so that the far parts move less (parallax).

    dusk    a sky that goes from deep violet to a warm horizon, stars that twinkle, a moon, drifting clouds and two ranges of hills
"""
import math

NAMES = ("dusk",)


def _lerp(a, b, t):
    return tuple(x + (y - x) * t for x, y in zip(a, b))


def _rand(i):
    """A repeatable number in 0..1 for i (the stars stay where they are)."""
    x = math.sin(i * 12.9898 + 78.233) * 43758.5453
    return x - math.floor(x)


def _box(flat, x, y, hw, hh, color, alpha=1.0, shape=0):
    flat.extend((x, y, hw, hh, 0.0, color[0], color[1], color[2], alpha, shape, 0, 0))


def dusk(vp, flat):
    """Adds the backdrop's sprites (the viewport's sprite batch: x, y, half w, half h, angle, r, g, b, a, shape, layer, 0) to `flat`."""
    aspect = vp.width / float(vp.height)
    cx, cy, half = vp.cx, vp.cy, vp.half
    w = half * aspect * 2.0 + 4.0
    top, bottom = cy + half + 1.0, cy - half - 1.0
    horizon = 1.0                                   # where the sky meets the hills (the level's ground is at about 4)
    # the sky: bands from the top (violet) to the horizon (warm)
    bands = 18
    sky_top, sky_mid, sky_low = (0.07, 0.06, 0.18), (0.26, 0.14, 0.38), (0.78, 0.36, 0.34)
    for i in range(bands):
        t = i / (bands - 1.0)
        c = _lerp(sky_top, sky_mid, t / 0.55) if t < 0.55 else _lerp(sky_mid, sky_low, (t - 0.55) / 0.45)
        y0 = top - (top - horizon) * i / bands
        y1 = top - (top - horizon) * (i + 1) / bands
        _box(flat, cx, (y0 + y1) / 2.0, w / 2.0, (y0 - y1) / 2.0 + 0.02, c)
    _box(flat, cx, (horizon + bottom) / 2.0 - 0.01, w / 2.0, (horizon - bottom) / 2.0 + 0.02, (0.10, 0.07, 0.16))     # below the horizon
    # stars (they hardly move) and the moon
    for i in range(70):
        sx = (_rand(i) * 120.0) - 10.0 - cx * 0.04 + cx
        sx = cx + ((_rand(i) * 2.0 - 1.0) * (half * aspect + 3.0))
        sx -= (cx * 0.04) % 1.0 * 0.0
        sy = cy + half * (0.15 + _rand(i + 100) * 0.85)
        tw = 0.45 + 0.55 * (0.5 + 0.5 * math.sin(vp.clock * (1.0 + _rand(i + 200) * 2.5) + i))
        size = 0.05 + 0.07 * _rand(i + 300)
        _box(flat, sx + (cx * -0.04), sy, size, size, (1.0, 0.97, 0.85), tw)
    mx, my = cx + half * aspect * 0.55 - cx * 0.03, cy + half * 0.62
    _box(flat, mx, my, 1.15, 1.15, (0.98, 0.95, 0.80), 0.14, 1)          # a glow
    _box(flat, mx, my, 0.8, 0.8, (0.97, 0.94, 0.78), 1.0, 1)
    _box(flat, mx + 0.25, my + 0.15, 0.2, 0.2, (0.88, 0.84, 0.68), 1.0, 1)      # craters
    _box(flat, mx - 0.2, my - 0.2, 0.14, 0.14, (0.88, 0.84, 0.68), 1.0, 1)
    # clouds drifting
    for i in range(6):
        speed = 0.25 + 0.1 * _rand(i)
        span = half * aspect * 2.0 + 14.0
        x = (_rand(i + 50) * span + vp.clock * speed - cx * 0.15) % span - span / 2.0 + cx
        y = cy + half * (0.1 + 0.55 * _rand(i + 70))
        s = 0.9 + _rand(i + 90)
        col = (0.55, 0.38, 0.55)
        for dx, dy, r in ((0.0, 0.0, 1.0), (1.1, -0.1, 0.8), (-1.1, -0.15, 0.75), (0.5, 0.35, 0.7)):
            _box(flat, x + dx * s, y + dy * s, r * s * 0.85, r * s * 0.5, col, 0.55, 1)
    # two ranges of hills, far and near: columns whose height is a sum of waves
    ground = 0.0
    for depth, par, base, amp, col, step in ((0, 0.30, 3.2, 3.2, (0.20, 0.13, 0.30), 0.5), (1, 0.55, 1.2, 2.2, (0.13, 0.10, 0.22), 0.5)):
        left = cx - half * aspect - 2.0
        x = math.floor((left - cx * (1 - par)) / step) * step
        end = cx + half * aspect + 2.0
        while x + cx * (1 - par) < end:
            wx = x + cx * (1 - par)
            h = base + amp * (0.5 + 0.5 * math.sin(x * 0.21 + depth * 2.0)) + 0.9 * math.sin(x * 0.53 + depth) + 0.5 * math.sin(x * 1.3)
            h = max(0.6, h)
            _box(flat, wx, ground + h / 2.0 - 3.0, step / 2.0 + 0.01, h / 2.0 + 3.0, col)
            x += step


def draw(name, vp, flat):
    if name == "dusk":
        dusk(vp, flat)

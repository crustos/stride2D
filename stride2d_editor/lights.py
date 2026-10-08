"""Lights in a level. A light has a place in the level (in cells: x to the right, y down from the top edge, so a light at (3.5, 2.5) is over the middle of the tile in
column 3, row 2), a radius in cells, and the rest. The viewport turns them, every frame, into one `scene_lights` effect (src/native/gfx2d/fx/scene_lights.fx) whose positions are
fractions of the window for the camera it has just then, so a light stays where it was put while the camera pans and zooms. A level holds up to MAX_LIGHTS lights; the effect
takes MAX_SHADER_LIGHTS, so each frame it gets the ones that matter to the camera (those whose light reaches the picture, the nearest to its middle first)."""
import math

MAX_LIGHTS = 64             # lights in a level
MAX_SHADER_LIGHTS = 8       # lights in one picture: scene_lights.fx
KINDS = ("point", "spot")
FALLOFFS = ("Linear", "Smooth", "Quadratic")

DEFAULT_LIGHTING = {"enabled": True, "ambient": [0.18, 0.2, 0.3, 1.0], "falloff": 1, "glow": 0.15, "exposure": 1.0}

# name, type, min, max, label: what the light's controls are (x and y run to the level's size)
LIGHT_SPECS = [
    {"name": "kind", "type": "enum", "options": ["Point", "Spot"], "label": "Kind", "default": [0]},
    {"name": "x", "type": "float", "min": 0.0, "max": 1.0, "label": "X (cells)", "default": [0.0]},
    {"name": "y", "type": "float", "min": 0.0, "max": 1.0, "label": "Y (cells)", "default": [0.0]},
    {"name": "radius", "type": "float", "min": 0.0, "max": 40.0, "label": "Radius (cells)", "default": [4.0]},
    {"name": "intensity", "type": "float", "min": 0.0, "max": 4.0, "label": "Intensity", "default": [1.0]},
    {"name": "color", "type": "color", "min": 0.0, "max": 1.0, "label": "Color", "default": [1.0, 0.9, 0.7, 1.0]},
    {"name": "angle", "type": "float", "min": -360.0, "max": 360.0, "label": "Direction (spot)", "default": [-90.0]},
    {"name": "cone", "type": "float", "min": 1.0, "max": 89.0, "label": "Cone half-angle (spot)", "default": [30.0]},
    {"name": "softness", "type": "float", "min": 0.0, "max": 1.0, "label": "Edge softness (spot)", "default": [0.4]},
]

LIGHTING_PARAMS = ("ambient", "falloff", "glow", "exposure")      # the first parameters of scene_lights: the level-wide ones


def new_light(kind, x, y):
    return {"kind": kind, "x": float(x), "y": float(y), "radius": 4.0, "intensity": 1.0, "color": [1.0, 0.9, 0.7, 1.0], "angle": -90.0, "cone": 30.0,
            "softness": 0.4, "enabled": True}


def _num(d, key, lo, hi, default):
    v = d.get(key, default)
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v):
        raise ValueError("%s: not a number: %r" % (key, v))
    return min(hi, max(lo, float(v)))


def _color(d, key, default):
    v = d.get(key, default)
    if not isinstance(v, (list, tuple)) or len(v) not in (3, 4) or any(isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(x) for x in v):
        raise ValueError("%s: a color is r, g, b (and a): %r" % (key, v))
    v = [min(1.0, max(0.0, float(x))) for x in v]
    return v + [1.0] if len(v) == 3 else v


def clean_light(d):
    """A checked copy of a light (numbers brought into their ranges); ValueError for what cannot be a light."""
    if not isinstance(d, dict):
        raise ValueError("a light is an object")
    if d.get("kind", "point") not in KINDS:
        raise ValueError("kind: %r is not one of %s" % (d.get("kind"), ", ".join(KINDS)))
    base = new_light(d.get("kind", "point"), 0, 0)
    return {"kind": d.get("kind", "point"), "x": _num(d, "x", -1000, 1000, 0), "y": _num(d, "y", -1000, 1000, 0),
            "radius": _num(d, "radius", 0, 40, base["radius"]), "intensity": _num(d, "intensity", 0, 4, base["intensity"]),
            "color": _color(d, "color", base["color"]), "angle": _num(d, "angle", -360, 360, base["angle"]), "cone": _num(d, "cone", 1, 89, base["cone"]),
            "softness": _num(d, "softness", 0, 1, base["softness"]), "enabled": bool(d.get("enabled", True))}


def clean_lighting(d):
    if not isinstance(d, dict):
        raise ValueError("lighting is an object")
    out = {"enabled": bool(d.get("enabled", True)), "ambient": _color(d, "ambient", DEFAULT_LIGHTING["ambient"]),
           "falloff": int(round(_num(d, "falloff", 0, 2, 1))), "glow": _num(d, "glow", 0, 1, 0.15), "exposure": _num(d, "exposure", 0, 4, 1)}
    return out


def effect_values(level, cx, cy, half, aspect):
    """The values of the `scene_lights` effect for `level` seen by a camera centered on (cx, cy) world units, `half` units up and down, `aspect` wide per high; None if
    nothing is lit (lighting switched off, or no light is on). World units are cells, y up: the level's top edge is at y = level.height."""
    lg = level.lighting
    lights = [l for l in level.lights if l["enabled"]]
    if not lg["enabled"] or not lights or half <= 0:
        return None
    if len(lights) > MAX_SHADER_LIGHTS:
        hw = half * aspect
        vy = level.height - cy                                  # the camera's middle in the level's own coordinates (y down from the top)

        def reach(l):                                           # how far the light is from the picture, minus its radius: negative if it reaches in
            dx = max(abs(l["x"] - cx) - hw, 0.0)
            dy = max(abs(l["y"] - vy) - half, 0.0)
            return math.hypot(dx, dy) - l["radius"]
        near = [l for l in lights if reach(l) < 0 and l["intensity"] > 0] or lights
        lights = sorted(near, key=lambda l: (l["x"] - cx) ** 2 + (l["y"] - vy) ** 2)
    lights = lights[:MAX_SHADER_LIGHTS]
    v = {"ambient": list(lg["ambient"]), "falloff": lg["falloff"], "glow": lg["glow"], "exposure": lg["exposure"], "mixAmt": 1.0}
    for i, l in enumerate(lights):
        v["l%dx" % i] = (l["x"] - cx) / (2.0 * half * aspect) + 0.5
        v["l%dy" % i] = 0.5 - ((level.height - l["y"]) - cy) / (2.0 * half)
        v["l%dr" % i] = l["radius"] / (2.0 * half)
        v["l%dk" % i] = l["intensity"]
        v["l%dc" % i] = list(l["color"])
        v["l%da" % i] = l["angle"]
        v["l%do" % i] = l["cone"]
        v["l%ds" % i] = l["softness"]
        v["l%dt" % i] = 1 if l["kind"] == "spot" else 0
    return v

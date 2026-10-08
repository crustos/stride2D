"""cave_demo.py: SlimeCave, a dark cave for the slime of SlimeJumpDestruct, lit with the 2D lights and dressed with the picture effects.

make_cave_project() is the cave as an editor project (stride2d.py --demo cave): a 100 x 18 level of rock, a bat-and-worm path, a cave-in of dirt, a pool, a spike pit and
a goal, with ~25 lights (torches, crystals, mushrooms, gems) and a stack of effects (colour grade, rising mist, vignette, a flash). The slime's own lantern is not in the
project: it is the one light that moves.

CaveSim is a stand-in for the sample's bot, in plain Python with no engine under it (so it runs anywhere the renderer does): the slime runs right, jumps what is in
the way, shoots what is in its line (worms, bats), digs through the dirt, picks up gems and walks to the flag. tools/cave_gif.py plays it through the renderer
(libgfx2d) and writes the animated GIF; cave_frame_lights() and cave_frame_effects() are what it hands the renderer each frame.
"""
import copy
import math
import random
from types import SimpleNamespace

from . import lights as L
from .asciiart import import_sprites
from .model import Level, Project, TileDef
from .slime_demo import SPRITES as SLIME_SPRITES

ROCK, DIRT, BACK, SLIME, WORM, BAT, SPIKE, GEM, GOAL, TORCH, CRYSTAL, MUSH, STALAC, POOL = (
    "\U0001faa8", "\U0001f7eb", "\U0001f311", "\U0001f7e2", "\U0001fab1", "\U0001f987", "\U0001f53a", "\U0001f48e", "\U0001f3c1",
    "\U0001f525", "\U0001f52e", "\U0001f344", "\U0001f53b", "\U0001f30a")

CAVE_SPRITES = """\
# sprite: rock
# fps: 0
# palette: a=#59617f b=#6f799c c=#3d4360
aabaaaca
abbaacca
aaaacaaa
caaabbaa
cccaabba
aabaaaac
abbaccaa
aaaacaaa

# sprite: backwall
# fps: 0
# palette: d=#3b4268 e=#323859
dddedddd
ddddddde
eddddddd
dddeedde
dddddddd
edddddde
dddeddde
dddddddd

# sprite: stalactite
# fps: 0
# palette: a=#59617f b=#6f799c c=#3d4360
aaaaaaaa
.abbaaa.
.aabaac.
..aabaa.
..aacb..
...aab..
...ac...
....a...

# sprite: crystal
# fps: 3
# palette: q=#7fe8ff u=#2a74d8 v=#b07cff
........
...W....
..qWq...
..qqqu..
.vqqquq.
.vvqquq.
vvvqquuq
vvvvuuuu

........
...q....
..qWq...
..qqWu..
.vqqquq.
.vvqquq.
vvvqquuq
vvvvuuuu

........
...W....
..qqq...
..qWqu..
.vqqWuq.
.vvqquq.
vvvqquuq
vvvvuuuu

# sprite: torch
# fps: 9
# palette: n=#6b4a2a
..Y.....
.YOY....
.YOOY...
..OR....
..n.....
..n.....
..n.....
..n.....

...Y....
..YOY...
..YOOY..
..OOR...
..n.....
..n.....
..n.....
..n.....

.Y......
.YOY....
..OOY...
..ORR...
..n.....
..n.....
..n.....
..n.....

# sprite: mushroom
# fps: 2
# palette: j=#5fe08a
........
..jjj...
.jjLjj..
jLjjjLj.
.TTTT...
...T....
...T....
..TTT...

........
..jjj...
.jjjjj..
jjLjjjL.
.TTTT...
...T....
...T....
..TTT...

# sprite: water
# fps: 2
# palette: s=#2a7fb8 t=#1b5c93 h=#8fe6ff
hshsshsh
ssssssss
sstssstt
tttttttt
tttttttt
tttttttt
tttttttt
tttttttt

shshsshs
ssssssss
sssttsst
tttttttt
tttttttt
tttttttt
tttttttt
tttttttt
"""

TILES = [          # emoji, name, sprite, solid, dynamic, diggable
    (ROCK, "cave rock", "rock", True, False, False),
    (DIRT, "loose dirt", "dirt", True, False, True),
    (BACK, "cave wall", "backwall", False, False, False),
    (SLIME, "slime", "slime", False, False, False),
    (WORM, "worm", "worm", False, False, False),
    (BAT, "bat", "bat", False, False, False),
    (SPIKE, "spikes", "spikes", False, False, False),
    (GEM, "gem", "gem", False, False, False),
    (GOAL, "goal", "goal", False, False, False),
    (TORCH, "torch", "torch", False, False, False),
    (CRYSTAL, "crystal", "crystal", False, False, False),
    (MUSH, "glow mushroom", "mushroom", False, False, False),
    (STALAC, "stalactite", "stalactite", False, False, False),
    (POOL, "pool", "water", False, False, False),
]

EMISSIVE = {TORCH, CRYSTAL, MUSH, GEM, GOAL}          # drawn after the lights: they give light, they are not lit
W, H = 100, 18


def _profile(x):
    """(ceiling row, floor row) of column x: the passage is the rows between them. The ceiling follows the ground (about 6 cells above it, never over the pits) so the
    camera sees both."""
    f = base = 12
    for start, row in ((13, 15), (18, 12), (31, 11), (34, 10), (37, 9), (61, 10), (65, 11), (69, 12), (72, 15), (77, 12)):
        if x >= start:
            f = row
            base = 12 if row == 15 else row
    c = base - 6 + round(1.3 * math.sin(x * 0.23) + 0.9 * math.sin(x * 0.071 + 1.3))
    return max(2, c), f


def make_cave_project():
    p = Project("SlimeCave")
    import_sprites(SLIME_SPRITES, p)
    import_sprites(CAVE_SPRITES, p)
    for key, rgb, name in (("E", (0xf2, 0xf2, 0xf2), "eyes"), ("V", (0x6b, 0x5a, 0x3c), "soil")):
        i = p.palette.index_of(key)
        p.palette.set_color(i, rgb)
        p.palette.entries[i].name = name
    for emoji, name, sprite, solid, dynamic, diggable in TILES:
        p.tiles[emoji] = TileDef(emoji, name, sprite, solid, dynamic, diggable)
    lv = Level("slime cave", W, H)

    def put(x, row, emoji):
        if 0 <= x < W and 0 <= row < H:
            lv.set(x, row, emoji)
    for x in range(W):
        c, f = _profile(x)
        for r in range(H):
            lv.set(x, r, ROCK if (r < c or r >= f or x < 2 or x >= W - 2) else BACK)
    for x in range(56, 59):                                               # the cave-in: loose dirt, all the way across the passage
        c, f = _profile(x)
        for r in range(c, f):
            put(x, r, DIRT)
    for x in range(13, 18):
        put(x, 14, POOL)
    for x in range(72, 77):
        put(x, 13, SPIKE)
    for x in range(3, 97, 5):                                             # stalactites under the ceiling, where nothing else hangs
        c, f = _profile(x)
        if lv.get(x, c) == BACK and x not in (23, 43, 53, 58, 68, 93):
            put(x, c, STALAC)
    for x in (4, 26, 45, 53, 68, 91):
        c, f = _profile(x)
        put(x, f - 4, TORCH)
    for x in (21, 35, 60, 80):
        put(x, _profile(x)[1] - 1, CRYSTAL)
    for x in (9, 28, 43, 62, 82):
        put(x, _profile(x)[1] - 1, MUSH)
    put(3, _profile(3)[1] - 1, SLIME)
    for x in (8, 21, 29, 41, 47, 52, 64, 74, 85, 93):
        put(x, _profile(x)[1] - 1 if x != 74 else 8, GEM)
    for x in (25, 44, 88):
        put(x, _profile(x)[1] - 1, WORM)
    for x in (34, 50, 82):
        put(x, _profile(x)[1] - 2, BAT)
    put(96, _profile(96)[1] - 1, GOAL)
    p.add_level(lv)
    p.empty = "⬛"
    lv.lighting = {"enabled": True, "ambient": [0.34, 0.37, 0.52, 1.0], "falloff": 2, "glow": 0.2, "exposure": 1.1}
    lv.lights = static_lights(lv)
    lv.effects = [
        {"effect": "hsv_adjust", "values": {"satScale": 1.12, "hueShift": -6.0}, "enabled": True},
        {"effect": "linear_gradient", "values": {"centerX": 0.5, "centerY": 0.9, "angle": 90.0, "period": 150.0, "waveAmp": 7.0, "waveFreq": 0.045,
                                                "color1": [0.25, 0.55, 0.62, 0.42], "color2": [0.25, 0.55, 0.62, 0.0], "curve": 1, "opacity": 1.0}, "enabled": True},
        {"effect": "bright_contrast", "values": {"brightness": 0.0, "contrast": 0.12}, "enabled": True},
        {"effect": "radial_gradient", "values": {"centerX": 0.5, "centerY": 0.5, "period": 330.0, "innerPeriod": 110.0,
                                                 "color1": [0.0, 0.0, 0.0, 0.0], "color2": [0.01, 0.015, 0.04, 0.8], "curve": 1, "opacity": 1.0}, "enabled": True},
        {"effect": "tint", "values": {"color": [1.0, 0.82, 0.3, 1.0], "amount": 0.0}, "enabled": True},
    ]
    p.dirty = False
    return p


LIGHT_OF = {      # emoji: (radius in cells, intensity, color)
    TORCH: (6.0, 1.3, (1.0, 0.52, 0.18, 1.0)),
    CRYSTAL: (5.0, 1.0, (0.38, 0.8, 1.0, 1.0)),
    MUSH: (3.6, 0.8, (0.4, 1.0, 0.55, 1.0)),
    GEM: (2.8, 0.8, (0.5, 0.95, 1.0, 1.0)),
    GOAL: (5.0, 1.0, (1.0, 0.95, 0.5, 1.0)),
    POOL: (4.0, 0.35, (0.3, 0.75, 1.0, 1.0)),
}


def static_lights(lv):
    """One light for each torch, crystal, mushroom, gem, the goal and the pool's middle, at the centre of its cell (x right, y down from the top edge)."""
    out = []
    for i, g in enumerate(lv.cells):
        if g in LIGHT_OF and not (g == POOL and (i % lv.width) != 15):
            r, k, col = LIGHT_OF[g]
            if g == CRYSTAL and (i % lv.width) in (35, 80):
                col = (0.72, 0.45, 1.0, 1.0)
            light = L.new_light("point", i % lv.width + 0.5, i // lv.width + 0.5)
            light.update(radius=r, intensity=k, color=list(col))
            out.append(light)
    return out


# ---------------------------------------------------------------------------------------------------------------------------------------------------
HW, HH = 0.4, 0.375             # the slime's half size
GRAVITY = -32.0
SPEED = 8.0
SHOOT_EVERY = 0.28


class CaveSim:
    """The slime and the cave, one step at a time (step(dt)). Everything is in world units (a cell is a unit, y up); `cells` is the level's grid, row by row from the
    top, that the bullets dig into. Nothing here changes the project."""

    def __init__(self, project, level, seed=5):
        self.p, self.lv = project, level
        self.w, self.h = level.width, level.height
        self.solid_set = {k for k, t in project.tiles.items() if t.solid}
        self.dig_set = {k for k, t in project.tiles.items() if t.diggable}
        self.cells = list(level.cells)
        self.rng = random.Random(seed)
        self.t = 0.0
        self.worms, self.bats, self.gems = [], [], []
        self.goal = None
        for i, g in enumerate(level.cells):
            x, y = i % self.w + 0.5, self.h - i // self.w - 0.5
            if g == SLIME:
                self.x, self.y = x, y - 0.125
                self.cells[i] = BACK
            elif g == WORM:
                self.worms.append({"x": x, "y": y - 0.18, "home": x, "alive": True, "ph": x * 0.7})
                self.cells[i] = BACK
            elif g == BAT:
                self.bats.append({"x": x, "y": y, "hx": x, "hy": y, "alive": True, "ph": x * 0.37})
                self.cells[i] = BACK
            elif g == GOAL:
                self.goal = (x, y)
        self.vx = self.vy = 0.0
        self.face = 1
        self.ground = False
        self.bullets, self.shards, self.sparks, self.flashes = [], [], [], []
        self.shoot_t = self.jump_t = 0.0
        self.gems_taken = 0
        self.flash = 0.0                  # the gold flash after a gem, 1 -> 0
        self.done = False
        self.done_t = 0.0
        self.frame = 0
        self.log = []
        self.cx, self.cy, self.half = self.x + 3, self.y + 1, 6.0
        self.static = [(l, self._source(l)) for l in level.lights]

    # ---- the world
    def _source(self, light):
        i = int(light["y"]) * self.w + int(light["x"])
        return i, self.lv.cells[i]

    def solid_cell(self, gx, gy):
        row = self.h - 1 - gy
        if gx < 0 or gx >= self.w or row < 0 or row >= self.h:
            return True
        return self.cells[row * self.w + gx] in self.solid_set

    def solid(self, x, y):
        return self.solid_cell(int(math.floor(x)), int(math.floor(y)))

    def _hit(self, x, y):
        for gx in range(int(math.floor(x - HW)), int(math.floor(x + HW - 1e-6)) + 1):
            for gy in range(int(math.floor(y - HH)), int(math.floor(y + HH - 1e-6)) + 1):
                if self.solid_cell(gx, gy):
                    return True
        return False

    def _first_solid_ahead(self, reach):
        """The first solid cell on the slime's row within `reach`: its x, or None."""
        d = 0.6
        while d <= reach:
            if self.solid(self.x + self.face * d, self.y + 0.1):
                return self.x + self.face * d
            d += 0.25
        return None

    def _target(self):
        """What the bot shoots: ("worm"/"bat", thing) in its line within 8 cells with nothing solid between, or ("dirt", x) when the way is blocked by diggable ground."""
        for kind, things in (("worm", self.worms), ("bat", self.bats)):
            for e in things:
                dx = (e["x"] - self.x) * self.face
                if e["alive"] and 1.5 < dx < 8.0 and abs(e["y"] - self.y) < 0.75:
                    wall = self._first_solid_ahead(dx)
                    if wall is None:
                        return kind, e
        wall = self._first_solid_ahead(5.0)
        if wall is not None and self.cells[(self.h - 1 - int(math.floor(self.y + 0.1))) * self.w + int(math.floor(wall))] in self.dig_set:
            return "dirt", wall
        return None

    # ---- one step
    def step(self, dt):
        self.t += dt
        self.flash = max(0.0, self.flash - dt * 3.0)
        self._enemies()
        if not self.done:
            self._bot(dt)
        else:
            self.done_t += dt
            self.vx = 0.0
        self._move(dt)
        self._bullets(dt)
        self._shards(dt)
        self._pickups()
        self.flashes = [f for f in self.flashes if self.t - f[0] < f[3]]
        self._camera()

    def _bot(self, dt):
        self.shoot_t -= dt
        self.jump_t -= dt
        tgt = self._target()
        if self.goal and abs(self.x - self.goal[0]) < 0.8:
            self.done = True
            self.log.append("goal reached at t=%.2f s" % self.t)
            for _ in range(40):
                self._spark(self.goal[0], self.goal[1] + 0.5, (1.0, 0.9, 0.4), 6.0)
            return
        if tgt and self.ground:
            self.vx = 0.0
            if self.shoot_t <= 0:
                self.shoot_t = SHOOT_EVERY
                self.bullets.append({"x": self.x + self.face * 0.7, "y": self.y + 0.1, "vx": self.face * 28.0, "t": 0.0})
                self.flashes.append((self.t, self.x + self.face * 0.9, self.y + 0.1, 0.12, (1.0, 0.85, 0.4), 4.0, 1.4))
            return
        if self.ground:
            self.vx = SPEED * self.face
            ahead = self.x + self.face * (HW + 0.55)
            wall = self.solid(ahead, self.y) or self.solid(ahead, self.y + 0.3)
            floor_ahead = any(self.solid(self.x + self.face * 1.0, self.y - HH - d) for d in (0.3, 1.1, 1.9))
            if self.jump_t <= 0 and (wall or not floor_ahead):
                self.vy = 14.0
                self.vx = SPEED * 1.08 * self.face
                self.jump_t = 0.5
                self.ground = False
        elif self.jump_t > 0:
            self.vx = SPEED * 1.08 * self.face            # in the air the slime keeps going (a wall's push stopped it for a step, not for the jump)

    def _move(self, dt):
        self.vy += GRAVITY * dt
        nx = self.x + self.vx * dt
        if self._hit(nx, self.y):
            nx = (math.floor(nx + HW) - HW - 1e-4) if self.vx > 0 else (math.floor(nx - HW) + 1 + HW + 1e-4)
            self.vx = 0.0
        self.x = nx
        ny = self.y + self.vy * dt
        self.ground = False
        if self._hit(self.x, ny):
            if self.vy > 0:
                ny = math.floor(ny + HH) - HH - 1e-4
            else:
                ny = math.floor(ny - HH) + 1 + HH + 1e-4
                self.ground = True
            self.vy = 0.0
        self.y = ny

    def _enemies(self):
        for w in self.worms:
            if w["alive"]:
                w["x"] = w["home"] + 0.8 * math.sin(self.t * 1.3 + w["ph"])
        for b in self.bats:
            if b["alive"]:
                b["x"] = b["hx"] + 2.6 * math.sin(self.t * 0.9 + b["ph"])
                b["y"] = b["hy"] + 1.3 * math.sin(self.t * 2.1 + b["ph"] * 2)

    def _bullets(self, dt):
        for b in list(self.bullets):
            b["x"] += b["vx"] * dt
            b["t"] += dt
            hit = None
            for e in self.worms + self.bats:
                if e["alive"] and abs(e["x"] - b["x"]) < 0.6 and abs(e["y"] - b["y"]) < 0.55:
                    hit = e
                    break
            gx, gy = int(math.floor(b["x"])), int(math.floor(b["y"]))
            if hit is not None:
                self._burst(hit)
            elif self.solid_cell(gx, gy):
                row = self.h - 1 - gy
                if 0 <= gx < self.w and 0 <= row < self.h and self.cells[row * self.w + gx] in self.dig_set:
                    self._crater(b["x"] + 0.5 * math.copysign(1, b["vx"]), b["y"], 1.5)
                else:
                    for _ in range(6):
                        self._spark(b["x"], b["y"], (1.0, 0.9, 0.5), 3.0)
            elif b["t"] < 1.0:
                continue
            self.bullets.remove(b)

    def _crater(self, cx, cy, radius):
        dug = 0
        for gy in range(int(cy - radius - 1), int(cy + radius + 2)):
            for gx in range(int(cx - radius - 1), int(cx + radius + 2)):
                row = self.h - 1 - gy
                if 0 <= gx < self.w and 0 <= row < self.h and self.cells[row * self.w + gx] in self.dig_set \
                        and (gx + 0.5 - cx) ** 2 + (gy + 0.5 - cy) ** 2 <= radius * radius + 0.3:
                    self.cells[row * self.w + gx] = BACK
                    dug += 1
                    for _ in range(3):
                        self._shard(gx + 0.5, gy + 0.5, (0.54, 0.35, 0.18), 0.18, 4.0)
        self.flashes.append((self.t, cx, cy, 0.25, (1.0, 0.75, 0.4), 5.0, 1.6))
        self.log.append("crater at x=%.1f (%d cells)" % (cx, dug))

    def _burst(self, e):
        e["alive"] = False
        col = (0.88, 0.24, 0.7) if e in self.worms else (0.55, 0.24, 0.88)
        for _ in range(16):
            self._shard(e["x"], e["y"], col, 0.28, 6.0)
        for _ in range(14):
            self._spark(e["x"], e["y"], col, 5.0)
        self.flashes.append((self.t, e["x"], e["y"], 0.45, col, 6.0, 1.8))
        self.log.append("%s burst at x=%.1f" % ("worm" if e in self.worms else "bat", e["x"]))

    def _shard(self, x, y, color, size, speed):
        a = self.rng.uniform(0, math.tau)
        s = self.rng.uniform(0.3, 1.0) * speed
        shade = self.rng.uniform(0.75, 1.15)
        self.shards.append({"x": x, "y": y, "vx": math.cos(a) * s, "vy": abs(math.sin(a)) * s + 2.0, "size": size * self.rng.uniform(0.5, 1.0),
                            "rot": self.rng.uniform(0, 3), "vrot": self.rng.uniform(-8, 8), "color": tuple(min(1.0, c * shade) for c in color), "t": 0.0})

    def _spark(self, x, y, color, speed):
        a = self.rng.uniform(0, math.tau)
        s = self.rng.uniform(0.3, 1.0) * speed
        self.sparks.append({"x": x, "y": y, "vx": math.cos(a) * s, "vy": math.sin(a) * s, "color": color, "t": 0.0, "ttl": self.rng.uniform(0.3, 0.7)})

    def _shards(self, dt):
        for s in list(self.shards):
            s["t"] += dt
            s["vy"] += GRAVITY * 0.8 * dt
            nx = s["x"] + s["vx"] * dt
            if self.solid(nx, s["y"]):
                s["vx"] *= -0.3
            else:
                s["x"] = nx
            ny = s["y"] + s["vy"] * dt
            if self.solid(s["x"], ny):
                s["vy"] *= -0.3
                s["vx"] *= 0.7
                s["vrot"] *= 0.5
                if abs(s["vy"]) < 1.0:
                    s["vy"] = 0.0
            else:
                s["y"] = ny
            s["rot"] += s["vrot"] * dt
            if s["t"] > 6.0:
                self.shards.remove(s)
        for s in list(self.sparks):
            s["t"] += dt
            s["x"] += s["vx"] * dt
            s["y"] += s["vy"] * dt
            s["vy"] += GRAVITY * 0.3 * dt
            if s["t"] > s["ttl"]:
                self.sparks.remove(s)

    def _pickups(self):
        for i, g in enumerate(self.cells):
            if g == GEM:
                gx, gy = i % self.w + 0.5, self.h - i // self.w - 0.5
                if abs(gx - self.x) < 0.8 and abs(gy - self.y) < 0.9:
                    self.cells[i] = BACK
                    self.gems_taken += 1
                    self.flash = 1.0
                    for _ in range(18):
                        self._spark(gx, gy, (0.6, 0.95, 1.0), 4.5)
                    self.flashes.append((self.t, gx, gy, 0.35, (0.6, 0.95, 1.0), 5.0, 1.6))
                    self.log.append("gem %d" % self.gems_taken)

    def _camera(self):
        aspect = 16.0 / 9.0
        hw = self.half * aspect
        tx = min(max(self.x + 3.5 * self.face, hw), self.w - hw)
        ty = min(max(self.y + 1.2, self.half), self.h - self.half)
        self.cx += (tx - self.cx) * 0.08
        self.cy += (ty - self.cy) * 0.08


def cave_frame_lights(sim):
    """The lights of this frame, as a level-like object for lights.effect_values: the level's own (the torches flicker, the crystals breathe, a gem's goes when it is
    taken), the slime's lantern (a spot in front of it and a glow around it), and the short flashes of shots, craters and bursts."""
    lights = []
    t = sim.t
    for light, (i, glyph) in sim.static:
        if sim.cells[i] != glyph and glyph != POOL:
            continue
        l = copy.deepcopy(light)
        ph = light["x"] * 1.7
        if glyph == TORCH:
            l["intensity"] *= 1.0 + 0.16 * math.sin(t * 13 + ph) + 0.09 * math.sin(t * 31 + 2 * ph) + 0.05 * math.sin(t * 7.3 + ph)
            l["radius"] *= 1.0 + 0.04 * math.sin(t * 9 + ph)
        elif glyph == CRYSTAL:
            l["intensity"] *= 0.85 + 0.2 * math.sin(t * 1.8 + ph)
        elif glyph == MUSH:
            l["intensity"] *= 0.9 + 0.12 * math.sin(t * 2.4 + ph)
        elif glyph == GEM:
            l["intensity"] *= 0.8 + 0.3 * math.sin(t * 4 + ph)
        lights.append(l)
    ly = sim.h - (sim.y + 0.25)
    lantern = L.new_light("spot", sim.x + sim.face * 0.3, ly)
    lantern.update(radius=9.0, intensity=0.95, color=[1.0, 0.88, 0.62, 1.0], angle=(0.0 if sim.face > 0 else 180.0) - 6.0 * sim.face, cone=34.0, softness=0.55)
    halo = L.new_light("point", sim.x, ly)
    halo.update(radius=2.4, intensity=0.6, color=[1.0, 0.95, 0.8, 1.0])
    lights += [lantern, halo]
    for b in sim.bullets:
        g = L.new_light("point", b["x"], sim.h - b["y"])
        g.update(radius=3.0, intensity=1.0, color=[1.0, 0.85, 0.35, 1.0])
        lights.append(g)
    for born, x, y, ttl, col, radius, k in sim.flashes:
        age = (t - born) / ttl
        g = L.new_light("point", x, sim.h - y)
        g.update(radius=radius * (0.6 + 0.6 * age), intensity=k * (1.0 - age) ** 2, color=list(col) + [1.0])
        lights.append(g)
    return SimpleNamespace(height=sim.h, lighting=sim.lv.lighting, lights=lights)


def cave_frame_effects(sim):
    """The level's effects with this frame's values: the mist ripples, the flash follows the last gem."""
    out = copy.deepcopy(sim.lv.effects)
    for fx in out:
        if fx["effect"] == "linear_gradient":
            fx["values"]["wavePhase"] = (sim.t * 1.1) % 6.28
        elif fx["effect"] == "tint":
            fx["values"]["amount"] = 0.28 * sim.flash * sim.flash
    return out

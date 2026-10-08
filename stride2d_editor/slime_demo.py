"""slime_demo.py: SlimeJumpDestruct (samples/SlimeJumpDestruct) as an editor project, and the driver that plays it in the viewport.

The sample is a headless C# game: a bot plays it and the program prints what happened. Its level is data in Level.cs (walls, which of them are ground you can
dig, spikes, vines, saves, gems, the goal, the two enemies), so the project is read from that file and drawn with sprites made here, in the editor's own
format. The eyes are one palette index, 'E': recolour it and the slime blinks.

SlimeDriver is a stand-in for the sample's bot, only to show the level moving in the viewport: the slime runs right, jumps what is in the way, shoots; a bullet
that lands on diggable ground digs a crater (the viewport removes the tiles) and the worm it kills bursts into Voronoi pieces (the engine's Destruction2D).
"""
import os
import random
import re

from .asciiart import import_sprites
from .model import Level, Project, TileDef

HERE = os.path.dirname(os.path.abspath(__file__))
SAMPLE = os.path.join(os.path.dirname(HERE), "samples", "SlimeJumpDestruct")

WALL, DIRT, SLIME, WORM, BAT, SPIKE, VINE, FLAG, GEM, GOAL = (
    "\U0001f9f1", "\U0001f7eb", "\U0001f7e2", "\U0001fab1", "\U0001f987", "\U0001f53a", "\U0001fa9c", "\U0001f6a9", "\U0001f48e", "\U0001f3c1")

SPRITES = """\
# sprite: stone
# fps: 0
SSSSSSSS
SDDDSDDD
SDDDSDDD
SSSSSSSS
DDSDDDSD
DDSDDDSD
SSSSSSSS
SDDDSDDD

# sprite: dirt
NNVNNNVN
NVNNTNNN
NNNNNNVN
VNNNNNNN
NNTNNVNN
NNNNNNNV
NVNNVNNN
NNNNNNTN

# sprite: slime
# fps: 4
........
........
..LLL...
.GLGGGG.
GGGGGGGG
GEEGGEEG
GGGGGGGG
.GGGGGG.

........
........
........
..LLLL..
.GLGGGGG
GEEGGEEG
GGGGGGGG
GGGGGGGG

........
..LL....
.GLGGG..
.GGGGGG.
.GEEGEEG
.GGGGGG.
.GGGGGG.
..GGGG..

........
........
..LLL...
.GLGGGG.
GGGGGGGG
GEEGGEEG
GGGGGGGG
.GGGGGG.

# sprite: worm
# fps: 3
........
........
........
........
..MMM...
.MMMMMM.
MEMMMMEM
MMMMMMMM

........
........
........
...MMM..
..MMMMM.
.MMMMMMM
MEMMMMEM
MMMMMMMM

# sprite: bat
# fps: 5
P......P
PP....PP
PPP..PPP
PPPPPPPP
.PPEEPP.
..PPPP..
........
........

........
........
P......P
PP.PP.PP
PPPPPPPP
.PPEEPP.
..PPPP..
........

# sprite: spikes
# fps: 0
........
........
........
...R....
..RWR.R.
.RRWRRRR
RRRRRRRR
RRRRRRRR

# sprite: vine
# fps: 0
.G.....G
.GG...GG
..G..GG.
..GGGG..
..LGG...
..GG.L..
.GG..GG.
.G....G.

# sprite: flag
# fps: 0
.DYYYY..
.DYYYYY.
.DYYYY..
.D......
.D......
.D......
.D......
DDD.....

# sprite: gem
# fps: 3
........
..CCCC..
.CWWCCC.
CWCCCCCB
.CCCCCB.
..CCCB..
...CB...
........

........
..CCCC..
.CCWWCC.
CCWCCCCB
.CCCCCB.
..CCCB..
...CB...
........

# sprite: goal
# fps: 2
DWDWDWDW
WDWDWDWD
DWDWDWDW
WDWDWDWD
.D......
.D......
.D......
.D......

DWDWDWDW
WDWDWDWD
DWDWDWDW
WDWDWDWD
D.......
D.......
D.......
D.......
"""

TILES = [          # emoji, name, sprite, solid, dynamic, diggable
    (WALL, "stone wall", "stone", True, False, False),
    (DIRT, "dirt", "dirt", True, False, True),
    (SLIME, "slime", "slime", False, False, False),
    (WORM, "worm", "worm", False, False, False),
    (BAT, "bat", "bat", False, False, False),
    (SPIKE, "spikes", "spikes", False, False, False),
    (VINE, "vines", "vine", False, False, False),
    (FLAG, "save flag", "flag", False, False, False),
    (GEM, "gem", "gem", False, False, False),
    (GOAL, "goal", "goal", False, False, False),
]


def _read(name):
    with open(os.path.join(SAMPLE, name), encoding="utf-8") as f:
        return f.read()


def _nums(text, array):
    """Every `Set4(array, i, a, b, c, d)` / `Set2(array, i, a, b)` of Level.Init, as lists of floats."""
    out = []
    for m in re.finditer(r"Set[24]\(%s,\s*\d+,\s*([^)]*)\)" % array, text):
        out.append([float(v.strip().rstrip("f")) for v in m.group(1).split(",")])
    return out


def make_slime_project():
    """The SlimeJumpDestruct level as a project: one level, 64 x 20 cells (a cell is a unit)."""
    level_cs = _read("Level.cs")
    p = Project("SlimeJumpDestruct")
    import_sprites(SPRITES, p)
    for key, rgb, name in (("E", (0xf2, 0xf2, 0xf2), "eyes"), ("V", (0x6b, 0x5a, 0x3c), "soil")):     # the letters the sprites use that the defaults lack
        i = p.palette.index_of(key)
        p.palette.set_color(i, rgb)
        p.palette.entries[i].name = name
    for emoji, name, sprite, solid, dynamic, diggable in TILES:
        p.tiles[emoji] = TileDef(emoji, name, sprite, solid, dynamic, diggable)
    width = int(re.search(r"maxX = (\d+)f", level_cs).group(1))
    height = int(re.search(r"maxY = (\d+)f", level_cs).group(1))
    lv = Level("slime jump destruct", width, height)

    def put(x, y, emoji, only_empty=False):        # x, y in world units from the bottom left; the grid is row by row from the top
        cx, cy = int(x), height - 1 - int(y)
        if 0 <= cx < width and 0 <= cy < height and not (only_empty and lv.get(cx, cy)):
            lv.set(cx, cy, emoji)

    def fill(rects, emoji):
        for x, y, w, h in rects:
            for i in range(int(w)):
                for j in range(int(h)):
                    put(x + i, y + j, emoji)

    fill(_nums(level_cs, "Climbs"), VINE)
    fill(_nums(level_cs, "Spikes"), SPIKE)
    diggable = re.search(r"WallDiggable\(int i\)\s*\{\s*return ([^;]*);", level_cs)
    dig = {int(n) for n in re.findall(r"i == (\d+)", diggable.group(1))} if diggable else set()
    for i, rect in enumerate(_nums(level_cs, "Walls")):                  # bedrock stays stone; the platforms and the tower are ground (a terrain in the sample)
        fill([rect], DIRT if i in dig else WALL)
    for x, y in _nums(level_cs, "Saves"):
        put(x, y, FLAG)
    for x, y in _nums(level_cs, "Gems"):
        put(x, y, GEM)
    m = re.search(r"goalX = ([\d.]+)f; goalY = ([\d.]+)f", level_cs)
    put(float(m.group(1)), float(m.group(2)), GOAL)
    m = re.search(r"spawnX = ([\d.]+)f; spawnY = ([\d.]+)f", level_cs)
    put(float(m.group(1)), float(m.group(2)), SLIME)
    for kind, x, y in re.findall(r"Enemies\[\d+\] = (\d+); Enemies\[\d+\] = ([\d.]+)f; Enemies\[\d+\] = ([\d.]+)f", level_cs):
        put(float(x), float(y), WORM if int(kind) == 0 else BAT)
    p.add_level(lv)
    p.empty = "⬛"
    p.dirty = False
    return p


BODY_STATIC, BODY_KINEMATIC, BODY_DYNAMIC = 0, 1, 2
PIT_RADIUS = 1.0                    # a dying enemy digs a pit this many units in radius where it stood (the sample's is 2 units across)
CRATER = 0.65                       # a bullet's crater, in units of radius (the sample's is 10 pixels across at 8 per unit)


class SlimeDriver:
    """A stand-in for the sample's bot, to show the level moving in the viewport (the real bot is C# in Bot.cs, headless). The slime runs right, jumps what is in
    the way, shoots the worm in its line, and climbs the tower to the goal. It plays on the viewport's own physics (a dynamic body that does not rotate): a bullet
    that lands on diggable ground digs a crater, and the worm it kills is replaced by a body of its size that the engine shatters (Voronoi) into pieces that
    fall into the pit left behind. Nothing here is the editor's data: stop and the level is as it was."""
    SPEED, SHOOT_EVERY = 8.0, 0.35

    def __init__(self):
        self.vp = None
        self.done = False

    # ---- the world as the bot sees it
    def cell(self, x, y):
        vp = self.vp
        cx, cy = int(x // 1), vp.level.height - 1 - int(y // 1)
        if 0 <= cx < vp.level.width and 0 <= cy < vp.level.height:
            return vp.cells[cy * vp.level.width + cx]
        return WALL

    def solid(self, x, y):
        t = self.vp.project.tiles.get(self.cell(x, y))
        return bool(t and t.solid and not t.dynamic)

    def start(self, vp):
        self.vp, self.lib = vp, vp.engine.lib
        lv = vp.level
        self.t, self.shoot_t, self.stun, self.jump_t = 0.0, 0.0, 0.0, 0.0
        self.done, self.won, self.log = False, False, []
        self.goal = self.spawn = None
        self.blink_t, self.blinking = 0.0, False
        self.pocket = 0
        for i, g in enumerate(lv.cells):
            x, y = i % lv.width, i // lv.width
            if g == SLIME:
                self.spawn = (x + 0.5, lv.height - y - 0.5)
                vp.cells[i] = ""
            elif g == GOAL:
                self.goal = (x + 0.5, lv.height - y - 0.5)
        e = self.lib
        self.node = e.p2d_new_node()
        e.p2d_set_pos(self.node, self.spawn[0], self.spawn[1] - 0.125 + 0.01)
        e.p2d_add_body_ex(self.node, BODY_DYNAMIC, 1, 1.0)
        e.p2d_add_box_ex(self.node, 0.9, 0.75, 0.0)
        self.actor = {"node": self.node, "tile": SLIME, "w": 1.0, "h": 1.0, "ttl": None, "dy": 0.125, "frame": 0}
        vp.actors.append(self.actor)
        vp.cx, vp.cy, vp.half = self.spawn[0] + 4, 8.0, 7.0
        pal = vp.project.palette
        self.eye = pal.index_of("E")
        self.eye_white = tuple(pal.entries[self.eye].rgb)

    def stop(self):
        self.vp = None

    @property
    def pos(self):
        return self.lib.p2d_node_x(self.node), self.lib.p2d_node_y(self.node)

    # ---- one physics step
    def step(self, dt):
        vp, e = self.vp, self.lib
        if vp is None or self.done:
            return
        self.t += dt
        x, y = self.pos
        vx, vy = e.p2d_velocity_x(self.node), e.p2d_velocity_y(self.node)
        on_ground = abs(vy) < 0.5 and (self.solid(x, y - 0.5) or self.solid(x - 0.3, y - 0.5) or self.solid(x + 0.3, y - 0.5))
        self._blink(dt)
        self._bullets()
        self._pickups(x, y)
        self.stun = max(0.0, self.stun - dt)
        self.jump_t = max(0.0, self.jump_t - dt)
        if self.goal and abs(x - self.goal[0]) < 0.9 and abs(y - self.goal[1]) < 1.2:
            self.done = self.won = True
            e.p2d_set_velocity(self.node, 0.0, 0.0)
            self.log.append("goal reached at t=%.2f s" % self.t)
            return
        target = self._target(x, y)
        if self._climb(x, y):
            e.p2d_set_velocity(self.node, 2.0 if y < 13.3 else 6.0, 9.0)
            self.actor["frame"] = 3
        else:
            move = self.SPEED
            if target is not None:
                self.shoot_t -= dt
                if self.shoot_t <= 0:
                    self.shoot_t = self.SHOOT_EVERY
                    self._shoot(x, y)
                move = 0.0
            elif on_ground and self.jump_t <= 0 and self.stun <= 0 and not self._climb_zone(x):
                ahead = self.solid(x + 0.9, y - 0.2) or self.solid(x + 0.9, y + 0.2)
                pit = not self.solid(x + 1.0, y - 0.6) and not self.solid(x + 0.4, y - 0.6)
                if ahead:
                    e.p2d_set_velocity(self.node, 6.5, 13.0)
                    self.jump_t, move = 0.5, None
                elif pit:
                    e.p2d_set_velocity(self.node, 8.5, 12.0)
                    self.jump_t, move = 0.5, None
            if self.stun <= 0 and move is not None:
                e.p2d_set_velocity(self.node, move, vy)
            self.actor["frame"] = 3 if not on_ground else (int(self.t * 8) % 3 if move else 0)
        self._camera(x, y)

    def _climb_zone(self, x):
        return 54.5 < x < 57.2

    def _climb(self, x, y):
        """The tower at x 57 is 9 high with vines on its near face: the slime climbs it, then hops on top."""
        return 55.8 < x < 57.0 and y < 13.6 and self.solid(57.5, 8.0)

    def _worms(self):
        vp, lv = self.vp, self.vp.level
        return [(i, i % lv.width + 0.5, lv.height - i // lv.width - 0.5) for i, g in enumerate(vp.cells) if g == WORM]

    def _target(self, x, y):
        """Something to shoot: the worm in the line ahead, or (once, on the way up) the tower's face."""
        for i, wx, wy in self._worms():
            if 0 < wx - x < 8.0 and abs(wy - y) < 1.0 and self._clear(x, y, wx):
                return ("worm", wx, wy)
        if 55.0 < x < 56.0 and self.pocket < 3 and self.solid(57.5, y):          # the tower: a pocket dug in its face, as in the sample's picture
            return ("tower", 57.5, y)
        return None

    def _clear(self, x, y, tx):
        """No solid cell between the slime and x = tx on its row."""
        px = x + 0.7
        while px < tx - 0.5:
            if self.solid(px, y):
                return False
            px += 0.5
        return True

    def _shoot(self, x, y):
        e = self.lib
        node = e.p2d_new_node()
        if node < 0:
            return
        e.p2d_set_pos(node, x + 0.7, y + 0.1)
        e.p2d_add_body(node, BODY_KINEMATIC)
        e.p2d_set_velocity(node, 30.0, 0.0)
        self.vp.actors.append({"node": node, "tile": None, "w": 0.35, "h": 0.14, "ttl": 1.2, "color": (1.0, 0.9, 0.3), "bullet": True, "layer": 4})
        self.actor["frame"] = 1

    def _crater(self, cx, cy, radius):
        """Digs the diggable cells whose centre is within `radius` of (cx, cy) and rebuilds the static bodies. Returns how many went."""
        vp, lv = self.vp, self.vp.level
        dug = 0
        for gy in range(max(0, int(lv.height - cy - radius - 1)), min(lv.height, int(lv.height - cy + radius + 1))):
            for gx in range(max(0, int(cx - radius - 1)), min(lv.width, int(cx + radius + 1))):
                t = vp.project.tiles.get(vp.cells[gy * lv.width + gx])
                if t and t.diggable and (gx + 0.5 - cx) ** 2 + (lv.height - gy - 0.5 - cy) ** 2 <= radius * radius + 0.3:
                    vp.cells[gy * lv.width + gx] = ""
                    dug += 1
        if dug:
            vp._build_statics()
        return dug

    def _bullets(self):
        vp, e = self.vp, self.lib
        lv = vp.level
        for b in [a for a in vp.actors if a.get("bullet")]:
            bx, by = e.p2d_node_x(b["node"]), e.p2d_node_y(b["node"])
            hit = False
            cx, cy = int(bx // 1), lv.height - 1 - int(by // 1)
            if 0 <= cx < lv.width and 0 <= cy < lv.height:
                g = vp.cells[cy * lv.width + cx]
                t = vp.project.tiles.get(g)
                if t and t.diggable:
                    dug = self._crater(bx + 0.4, by, CRATER)
                    self.log.append("crater at x=%.1f (%d cells)" % (bx, dug))
                    self.pocket += 1
                    hit = True
                elif t and t.solid:
                    hit = True
            for i, wx, wy in self._worms():
                if abs(wx - bx) < 0.5 and abs(wy - by) < 0.5:
                    self._burst(i, wx, wy)
                    hit = True
            if hit:
                e.p2d_destroy_node(b["node"])
                vp.actors.remove(b)

    def _burst(self, i, wx, wy):
        """The worm is hit: it goes, and a body of its size is shattered by the engine into pieces; the ground it stood on is dug into a pit."""
        vp, e = self.vp, self.lib
        vp.cells[i] = ""
        body = e.p2d_new_node()
        if body >= 0:
            e.p2d_set_pos(body, wx, wy)
            e.p2d_add_body(body, BODY_DYNAMIC)
            e.p2d_add_box(body, 0.9, 0.6)
            made = vp.shatter({"node": body, "tile": WORM, "w": 0.9, "h": 0.6}, extra_points=3, speed=3.0)
            self.log.append("worm burst into %d pieces" % made)
        dug = self._crater(wx, wy - 0.6, PIT_RADIUS)
        self.log.append("pit dug (%d cells)" % dug)

    def _pickups(self, x, y):
        vp = self.vp
        lv = vp.level
        for i, g in enumerate(vp.cells):
            if g == GEM:
                gx, gy = i % lv.width + 0.5, lv.height - i // lv.width - 0.5
                if abs(gx - x) < 0.8 and abs(gy - y) < 0.9:
                    vp.cells[i] = ""
                    self.log.append("gem")

    def _blink(self, dt):
        """The eyes are one palette index: recolouring it is all a blink takes."""
        vp = self.vp
        self.blink_t += dt
        period, closed = 2.4, 0.16
        want = (self.blink_t % period) > period - closed
        if want != self.blinking:
            self.blinking = want
            pal = vp.project.palette
            green = pal.entries[pal.index_of("G")]
            dirty = vp.project.dirty                                 # playing is not an edit: do not ask to save because of a blink
            pal.set_color(self.eye, tuple(green.rgb) if want else self.eye_white)
            vp.project.touch()
            vp.project.dirty = dirty

    def _camera(self, x, y):
        vp = self.vp
        tx = min(max(x + 3.0, 12.0), vp.level.width - 12.0)
        ty = min(max(y + 1.5, 7.5), vp.level.height - 7.5)
        vp.cx += (tx - vp.cx) * 0.08
        vp.cy += (ty - vp.cy) * 0.08

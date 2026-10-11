"""slime_rust.py: SlimeJump (samples/SlimeJump), with its game logic in Rust, as an editor project.

The level is built below from rectangles of characters, the sprites are the ones of slime_demo plus three made here (crumbly, turret, anchor), and the scripts are the Rust
files of samples/SlimeJumpRust:

    Slime    the player: walk (arrows or A/D), jump (space, up or W; let go early for a short hop), climb vines, the blaster (left mouse button), the lasso (right mouse
             button; W / S reel, A / D swing), and back to the last checkpoint when hurt or fallen
    Bullet   the blaster's shot; kills worms          Worm     crawls to and fro; hurts from the side, is squashed from above
    Turret   shoots Arrows at the slime              Arrow    hurts
    Crumbly  a platform that dissolves a second after the slime stands on it       Vine     climbable      Anchor   something to throw the lasso at
    Save     checkpoint flag      Gem  picked up (kept at the next checkpoint)      Spikes  hurt      Goal  flag: its tag becomes 99
    Bot      (a game script) plays the level when switched on with the T key

The scripts talk through node tags (the engine's set_tag / get_tag) and a store of numbers (set_global / get_global): see the constants at the top of Slime.rs. The Rust is the
Crust subset (Crust lowers it to C, which is linked into the engine library by Build).
"""
import os

from .asciiart import import_sprites
from .model import Level, Project, ScriptFile, TileDef
from .slime_demo import FLAG, GEM, GOAL, SLIME, SPIKE, SPRITES, TILES, VINE, WALL, WORM

HERE = os.path.dirname(os.path.abspath(__file__))
SAMPLE = os.path.join(os.path.dirname(HERE), "samples", "SlimeJumpRust")

CRUMBLY, TURRET, ANCHOR = "\U0001f36a", "\U0001f3f9", "\u2693"

EXTRA_SPRITES = """\
# sprite: crumbly
# fps: 0
OOOOOOOO
ONNONNNO
ONNNNONO
OOOOOOOO
ONNONNNO
ONNNNNNO
ONONNNOO
OOOOOOOO

# sprite: turret
# fps: 0
SSSSSSSS
SDDDDDDS
SDRRRRDS
SDRWWRDS
SDRWWRDS
SDRRRRDS
SDDDDDDS
SSSSSSSS

# sprite: anchor
# fps: 0
..SSSS..
.SDDDDS.
SDD..DDS
SD....DS
SDD..DDS
.SDDDDS.
..SSSS..
...DD...
"""

W, H = 84, 16
SCRIPTS = ("Slime", "Worm", "Spikes", "Gem", "Goal", "Bullet", "Arrow", "Turret", "Crumbly", "Vine", "Anchor", "Save", "Bot")
SPRITE_OF = {"Slime": "slime", "Worm": "worm", "Spikes": "spikes", "Gem": "gem", "Goal": "goal", "Turret": "turret", "Crumbly": "crumbly", "Vine": "vine",
             "Anchor": "anchor", "Save": "flag"}
GAME_SCRIPTS = ("Bot",)          # (Bullet and Arrow are made by the Slime and the Turret, not placed in the level)
EXTRA_TILES = [(CRUMBLY, "crumbly platform", "crumbly", False, False, False), (TURRET, "turret", "turret", False, False, False), (ANCHOR, "anchor", "anchor", False, False, False)]
EMOJI = {"#": WALL, "S": SLIME, "w": WORM, "^": SPIKE, "g": GEM, "G": GOAL, "c": CRUMBLY, "t": TURRET, "a": ANCHOR, "v": VINE, "k": FLAG}


def level_rows():
    """The level as rows of characters, the top one first: from the left, flat ground with spikes and a worm, a pit, a checkpoint, crumbly platforms, a turret, a wall
    with vines to climb, a plateau with a checkpoint, a gap too wide to jump (an anchor to swing on), and the goal."""
    g = [["."] * W for _ in range(H)]

    def fill(x0, x1, y0, y1, ch):
        for y in range(y0, y1 + 1):
            for x in range(x0, x1 + 1):
                g[y][x] = ch
    fill(0, 0, 0, 15, "#")
    fill(W - 1, W - 1, 0, 15, "#")
    for x0, x1 in ((0, 19), (24, 30), (37, 51)):
        fill(x0, x1, 12, 15, "#")
    fill(31, 36, 12, 12, "c")
    fill(52, 58, 4, 15, "#")
    fill(70, W - 1, 4, 15, "#")
    fill(51, 51, 4, 11, "v")
    for x, y, ch in ((3, 11, "S"), (7, 11, "^"), (8, 11, "^"), (14, 11, "w"), (26, 11, "k"), (47, 11, "t"), (54, 3, "k"), (65, 2, "a"), (74, 3, "w"),
                     (77, 3, "^"), (78, 3, "^"), (80, 3, "G"),
                     (16, 11, "g"), (28, 11, "g"), (41, 11, "g"), (55, 3, "g"), (72, 3, "g")):
        g[y][x] = ch
    return ["".join(r) for r in g]


MAP = "\n".join(level_rows())


def red_slime(text):
    """The sprites of slime_demo with the slime in red (its green and light green are letters the vines use too, so the slime gets letters of its own)."""
    out = []
    for block in text.split("# sprite: "):
        if block.startswith("slime"):
            head, _, rest = block.partition("\n")
            lines = [ln if ln.startswith("#") else ln.replace("G", "Q").replace("L", "P") for ln in rest.split("\n")]
            block = head + "\n" + "\n".join(lines)
        out.append(block)
    return "# sprite: ".join(out)


def make_slime_rust_project():
    p = Project("SlimeJumpRust")
    import_sprites(red_slime(SPRITES), p)
    import_sprites(EXTRA_SPRITES, p)
    for key, rgb, name in (("E", (0xf2, 0xf2, 0xf2), "eyes"), ("V", (0x6b, 0x5a, 0x3c), "soil")):
        i = p.palette.index_of(key)
        p.palette.set_color(i, rgb)
        p.palette.entries[i].name = name
    for key, rgb, name in (("Q", (0xd8, 0x2f, 0x2f), "slime red"), ("P", (0xff, 0x8a, 0x78), "slime light")):
        i = p.palette.index_of(key)
        if i is None:
            raise AssertionError("the slime's palette letter %s was not made" % key)
        p.palette.set_color(i, rgb)
        p.palette.entries[i].name = name
    for emoji, name, sprite, solid, dynamic, diggable in list(TILES) + EXTRA_TILES:
        if emoji in EMOJI.values():
            p.tiles[emoji] = TileDef(emoji, name, sprite, solid, dynamic, diggable)
    rows = MAP.split("\n")
    lv = Level("slime jump", len(rows[0]), len(rows))
    for y, row in enumerate(rows):
        assert len(row) == lv.width, "row %d is %d cells, not %d" % (y, len(row), lv.width)
        for x, ch in enumerate(row):
            if ch in EMOJI:
                lv.set(x, y, EMOJI[ch])
    p.add_level(lv)
    for name in SCRIPTS:
        with open(os.path.join(SAMPLE, name + ".rs"), encoding="utf-8") as f:
            p.scripts.append(ScriptFile(name, f.read(), "rust"))
        if name in SPRITE_OF:
            p.sprite(SPRITE_OF[name]).scripts.append(name)
    p.game_scripts = list(GAME_SCRIPTS)
    p.backdrop = "dusk"
    p.empty = "⬛"
    p.dirty = False
    return p

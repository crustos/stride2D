"""engine.py: the 2D engine, from Python. libstride2d.so (built by tools/engine_so.py: the C# runtime translated to C, plus the renderer) is loaded with
ctypes; nothing here needs .NET.

    Engine    the library with its signatures declared: the p2d_* functions (the scene and its physics, from src/engine/Engine.cs) and the gfx_* functions
              (the renderer: textures, triangles, the window, input; src/native/gfx2d/gfx2d.h).
    Viewport  a window that shows a Level, animated, with a play mode in which the solid tiles are physics bodies and a click drops a ball. The engine's scene does the
              physics only; everything on screen is drawn through the renderer (one path), and the window's mouse and keyboard come back through gfx_poll_event.

One Engine per process (the C runtime has one scene and one renderer), driven from ONE thread: the Qt main thread, from a timer, as stride2d.py does it.
"""
import array
import math
import random
import ctypes as C
import os
import time

from . import scenery

ABI_VERSION = 8
_HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(_HERE)


class EngineError(RuntimeError):
    pass


def library_candidates():
    env = os.environ.get("STRIDE2D_LIB")
    return ([env] if env else []) + ["/tmp/libstride2d.so", os.path.join(ROOT, "build", "libstride2d.so")]


def find_library():
    for path in library_candidates():
        if os.path.isfile(path):
            return path
    return None


BUILD_HINT = "build it with:  python3 build.py so   (writes /tmp/libstride2d.so; needs the .NET SDK once, for the C# to C translator)"

# the p2d_* functions: name -> (result, argument types). Generated into libstride2d.h from src/engine/Engine.cs; check_api() compares.
_i, _f, _v = C.c_int, C.c_float, C.c_void_p
P2D = {
    "p2d_version": (_i, []), "p2d_init": (_i, [_i, _i]), "p2d_shutdown": (None, []),
    "p2d_camera": (None, [_f] * 6), "p2d_new_node": (_i, []), "p2d_node_count": (_i, []),
    "p2d_set_pos": (None, [_i, _f, _f]), "p2d_set_angle": (None, [_i, _f]), "p2d_set_scale": (None, [_i, _f, _f]),
    "p2d_node_x": (_f, [_i]), "p2d_node_y": (_f, [_i]), "p2d_node_angle": (_f, [_i]),
    "p2d_destroy_node": (None, [_i]), "p2d_clear": (None, []),
    "p2d_add_sprite": (_i, [_i, _i, _f, _f, _f, _f, _f]), "p2d_add_body": (_i, [_i, _i]),
    "p2d_add_box": (_i, [_i, _f, _f]), "p2d_add_circle": (_i, [_i, _f]), "p2d_gravity": (None, [_f, _f]),
    "p2d_set_velocity": (None, [_i, _f, _f]), "p2d_impulse": (None, [_i, _f, _f]), "p2d_velocity_x": (_f, [_i]), "p2d_velocity_y": (_f, [_i]),
    "p2d_add_body_ex": (_i, [_i, _i, _i, _f]), "p2d_add_box_ex": (_i, [_i, _f, _f, _f]), "p2d_add_box_trigger": (_i, [_i, _f, _f]), "p2d_blast": (_i, [_f, _f, _f, _f]),
    "p2d_step": (None, [_f]), "p2d_draw_sprites": (_i, []), "p2d_draw_meshes": (_i, [_i]),
    "p2d_sand_init": (_i, [_i, _i]), "p2d_sand_free": (None, []), "p2d_sand_seed": (None, [_i]), "p2d_sand_set": (_i, [_i, _i, _i]), "p2d_sand_brush": (_i, [_i] * 4),
    "p2d_sand_step": (_i, [_i]), "p2d_sand_draw": (_i, [_f] * 4), "p2d_sand_count": (_i, [_i]), "p2d_sand_hash": (_i, []),
    "p2d_script_count": (_i, []), "p2d_attach_script": (_i, [_i, _i]), "p2d_set_key": (None, [_i, _i]), "p2d_set_mouse": (None, [_f, _f, _i]), "p2d_clear_input": (None, []),
    "p2d_shatter": (_i, [_i, _i, _i]), "p2d_fragment": (_i, [_i]),
    "p2d_node_alive": (_i, [_i]), "p2d_set_tag": (None, [_i, _i]), "p2d_get_tag": (_i, [_i]),
    "p2d_node_slots": (_i, []), "p2d_node_active": (_i, [_i]), "p2d_set_active": (None, [_i, _i]), "p2d_sprite_info": (_f, [_i, _i]),
    "p2d_set_global": (None, [_i, _f]), "p2d_get_global": (_f, [_i]), "p2d_set_layer": (None, [_i, _i]), "p2d_collider_of": (_i, [_i]),
    "p2d_raycast": (_i, [_f, _f, _f, _f, _f, _i]), "p2d_ray_x": (_f, []), "p2d_ray_y": (_f, []), "p2d_overlap_box": (_i, [_f, _f, _f, _f, _i]),
    "p2d_math_sqrt": (_f, [_f]), "p2d_math_sin": (_f, [_f]), "p2d_math_cos": (_f, [_f]), "p2d_math_atan2": (_f, [_f, _f]), "p2d_key_down": (_i, [_i]), "p2d_mouse_down": (_i, [_i]), "p2d_mouse_world_x": (_f, []), "p2d_mouse_world_y": (_f, []),
}
GFX = {
    "gfx_begin": (None, []), "gfx_sprites": (_i, [_v, _i]), "gfx_end": (_i, []), "gfx_backend": (_i, []), "gfx_camera": (None, [_f] * 6), "gfx_pixel": (C.c_uint32, [_i, _i]), "gfx_frame_hash": (_i, []),
    "gfx_save_frame": (_i, [_i]), "gfx_stat": (_i, [_i]),
    "gfx_texture": (_i, [_i, _i, _i, _v]), "gfx_texture_update": (None, [_i, _i, _i, _i, _i, _v]), "gfx_texture_free": (None, [_i]),
    "gfx_triangles": (_i, [_v, _i, _i]), "gfx_clip": (_i, [_i] * 4), "gfx_clip_reset": (_i, []), "gfx_effect": (_i, [_i, _v, _i]),
    "gfx_poll_event": (_i, [_v]), "gfx_inject_event": (_i, [_i] * 5),
}

# Sand (src/terrain/SandSim.cs, driven by Engine.cs): stone, sand and water in a grid over the level, a picture the engine moves on the CPU.
SAND_AIR, SAND_STONE, SAND_SAND, SAND_WATER = range(4)
SAND_NAMES = {SAND_AIR: "Erase", SAND_STONE: "Stone", SAND_SAND: "Sand", SAND_WATER: "Water"}
SAND_MAX_CELLS = 400 * 400                    # the CPU simulation's grid: bigger levels get fewer cells to a tile


class SandSettings:
    """What the sand does in the viewport (the sand window edits it; the viewport reads it every frame). Not saved in the project."""

    def __init__(self):
        self.enabled = False
        self.element = SAND_SAND
        self.radius = 3             # the brush, in grid cells
        self.speed = 2              # simulation steps a frame
        self.scale = 8              # grid cells along a tile's side
        self.paused = False
        self.solid_stone = True     # the level's solid tiles are stone to the sand
        self.seed = 1
        self.generation = 0         # bumped to make the viewport start the grid again (Clear / Reload from the level)
        self.error = ""             # why the sand cannot run, if it cannot


# events (gfx2d.h)
EV_MOUSE_MOVE, EV_MOUSE_DOWN, EV_MOUSE_UP, EV_WHEEL, EV_KEY_DOWN, EV_KEY_UP, EV_TEXT, EV_FOCUS, EV_CLOSE = range(1, 10)
BTN_LEFT, BTN_MIDDLE, BTN_RIGHT = 0, 1, 2
KEY_ESCAPE, KEY_HOME, KEY_LEFT, KEY_RIGHT, KEY_DOWN, KEY_UP = 256, 268, 263, 262, 264, 265
BODY_STATIC, BODY_KINEMATIC, BODY_DYNAMIC = 0, 1, 2
FILTER_NEAREST = 0
STAT_WINDOWED = 4


def floats_ptr(arr):
    """The address of an array('f') (it must stay alive while the call runs)."""
    return arr.buffer_info()[0]


class Engine:
    def __init__(self, path=None):
        path = path or find_library()
        if not path:
            raise EngineError("libstride2d.so was not found (looked in %s): %s" % (", ".join(library_candidates()), BUILD_HINT))
        try:
            self.lib = C.CDLL(path)
        except OSError as e:
            raise EngineError("cannot load %s: %s" % (path, e))
        self.path = path
        for table in (P2D, GFX):
            for name, (res, args) in table.items():
                try:
                    fn = getattr(self.lib, name)
                except AttributeError:
                    raise EngineError("%s has no %s: it is older than this editor. %s" % (path, name, BUILD_HINT))
                fn.restype = res
                fn.argtypes = args
        v = self.lib.p2d_version()
        if v != ABI_VERSION:
            raise EngineError("%s is engine API version %d, this editor wants %d. %s" % (path, v, ABI_VERSION, BUILD_HINT))
        self.started = False
        self.script_ids = self._read_manifest(path)

    @staticmethod
    def _read_manifest(path):
        """{script class name: number} from OUT.scripts.json, which tools/engine_so.py --scripts writes beside the library: the numbers Engine.AttachScript takes."""
        import json
        try:
            with open(path + ".scripts.json", encoding="utf-8") as f:
                return {item["name"]: int(item["id"]) for item in json.load(f)}
        except (OSError, ValueError, KeyError, TypeError):
            return {}

    def unload(self):
        """Shuts the engine down and lets go of the library (its window must be closed first: Viewport.close). The Engine is not usable afterwards; make another from the new file."""
        self.stop()
        lib, self.lib = self.__dict__.pop("lib", None), None
        if lib is not None:
            try:
                import _ctypes
                _ctypes.dlclose(lib._handle)
            except (ImportError, OSError, AttributeError):
                pass                                      # (an old library stays loaded: harmless, the next one is another file)

    def __getattr__(self, name):
        """engine.new_node() is p2d_new_node, and engine.gfx_draw / engine.p2d_step name their functions in full: all plain library calls."""
        lib = self.__dict__.get("lib")
        if lib is None:
            raise AttributeError(name)
        return getattr(lib, name if name.startswith(("gfx_", "p2d_")) else "p2d_" + name)

    def effect(self, name, values=None):
        """Queues the effect `name` (see fxdefs.EFFECTS) with the parameter values {parameter: value} over what the frame has drawn so far, inside the current clip
        (gfx_effect). Returns True if it was queued. Call it between gfx_begin and gfx_end, after the draws it should change."""
        from .fx import pack
        eid, floats = pack(name, values)
        arr = array.array("f", floats)
        return bool(self.lib.gfx_effect(eid, floats_ptr(arr), len(floats)))

    def start(self, width, height, window=True):
        """Makes the renderer's picture and the scene. With an X display the renderer opens its window (window=False keeps it offscreen: STRIDE2D_HEADLESS);
        it draws on the GPU through EGL, or on the CPU when there is none."""
        if self.started:
            return
        if not window:
            os.environ["STRIDE2D_HEADLESS"] = "1"
        if self.lib.p2d_init(width, height) != 1:
            raise EngineError("the renderer could not start (STRIDE2D_GFX_DEBUG=1 says why)")
        self.started = True

    def stop(self):
        if self.started:
            self.lib.p2d_shutdown()
            self.started = False

    def poll_event(self):
        ev = (C.c_int * 5)()
        return tuple(ev) if self.lib.gfx_poll_event(ev) else None


# ---------------------------------------------------------------------------------------------------------------------------------------------------

def placeholder_color(emoji):
    """A steady colour for a tile that has no sprite, from the emoji itself."""
    h = 2166136261
    for ch in emoji:
        h = ((h ^ ord(ch)) * 16777619) & 0xFFFFFFFF
    return (0.35 + (h & 0xFF) / 700.0, 0.35 + ((h >> 8) & 0xFF) / 700.0, 0.35 + ((h >> 16) & 0xFF) / 700.0)


class Viewport:
    """The window. tick() is one frame: call it about 60 times a second from one thread."""
    BACKGROUND = (0.09, 0.10, 0.14)

    def __init__(self, engine, project, width=800, height=480):
        self.engine = engine
        self.project = project
        self.width, self.height = width, height
        self.level = None
        self.cx, self.cy, self.half = 0.0, 0.0, 6.0     # the camera: centre in world units and half the visible height
        self.playing = False
        self.balls = []                                  # engine node indexes
        self.cells = None                                # in play mode: a copy of the level's cells that blasts may dig into
        self.statics = []                                # the static boxes made from the solid cells
        self.actors = []                                 # movable tiles (crates) and debris: dicts with node, tile, w, h, ttl
        self.frag_tile = ""                              # the tile whose sprite textures the fragments of a shattered node
        self.driver = None                               # something with step(dt) and the viewport's play mode, e.g. slime_demo.SlimeDriver
        self.clock = 0.0
        self._last = None
        self._acc = 0.0
        self._textures = {}                              # (sprite name, frame) -> texture id
        self._tex_rev = None
        self._pan = None                                 # (mouse x, y, camera x, y) while a pan drag is running
        self.mouse = (width // 2, height // 2)
        self.closed = False
        self.status = ""
        self.sand = SandSettings()
        self._sand_key = None                            # (level, dims, generation) the grid was made for; None: not made
        self._sand_dims = None                           # (columns, rows, cells per tile) of the grid
        self._brush_from = None                          # the cell the brush was last at while the left button is down
        self.script_report = ""
        self._buttons = 0                                # the mouse buttons held (bit 0 left, 1 middle, 2 right), for scripts

    # ---- lifecycle
    def open(self):
        self.engine.start(self.width, self.height)
        if not self.engine.lib.gfx_stat(STAT_WINDOWED):          # the renderer opens its window by itself when there is an X display
            self.engine.stop()
            raise EngineError("the window could not open: is a display available (DISPLAY set; STRIDE2D_HEADLESS unset)? "
                              "STRIDE2D_GFX_DEBUG=1 says why the renderer chose what it did")
        self.closed = False
        self._sand_key = None                            # (the engine start made a new scene: the grid is gone)
        self._last = None
        if self.level is not None:
            self.fit()

    def close(self):
        self._stop_play()
        self._free_textures()
        self.engine.stop()                                       # the renderer's window goes with the renderer
        self.closed = True

    @property
    def is_open(self):
        return self.engine.started and bool(self.engine.lib.gfx_stat(STAT_WINDOWED)) and not self.closed

    # ---- the level and the camera
    def show_level(self, level):
        was_playing = self.playing
        self._stop_play()
        self.level = level
        if self.engine.started:
            self.fit()
        if was_playing:
            self._start_play()

    def fit(self):
        lv = self.level
        if lv is None:
            return
        self.cx, self.cy = lv.width / 2.0, lv.height / 2.0
        aspect = self.width / float(self.height)
        self.half = max(lv.height / 2.0 + 0.5, (lv.width / 2.0 + 0.5) / aspect)

    def screen_to_world(self, px, py):
        aspect = self.width / float(self.height)
        return (self.cx + (px / self.width - 0.5) * 2.0 * self.half * aspect, self.cy - (py / self.height - 0.5) * 2.0 * self.half)

    # ---- textures: one per sprite frame that a tile of the level uses
    def _free_textures(self):
        if self.engine.started:
            for tex in self._textures.values():
                self.engine.lib.gfx_texture_free(tex)
        self._textures = {}

    def _texture(self, sprite, frame):
        key = (sprite.name, frame)
        tex = self._textures.get(key)
        if tex is None:
            rgba = sprite.rgba(self.project.palette, frame)
            buf = (C.c_uint8 * len(rgba)).from_buffer_copy(rgba)
            tex = self.engine.lib.gfx_texture(sprite.width, sprite.height, FILTER_NEAREST, C.addressof(buf))
            self._textures[key] = tex            # 0 (no room: 63 textures) is remembered too, and the tile shows as a placeholder
        return tex

    def _sync_textures(self):
        rev = (self.project.revision, self.project.palette.version)
        if rev != self._tex_rev:
            self._free_textures()
            self._tex_rev = rev

    # ---- physics play mode
    def _start_play(self):
        lv = self.level
        e = self.engine.lib
        if lv is None:
            return
        e.p2d_clear()
        e.p2d_gravity(0.0, -18.0)
        self.cells = list(lv.cells)
        self.statics, self.actors, self.balls = [], [], []
        self._skipped = 0
        solid = {k for k, t in self.project.tiles.items() if t.dynamic}
        for y in range(lv.height):                        # movable tiles (crates) are bodies of their own
            for x in range(lv.width):
                g_ = self.cells[y * lv.width + x]
                if g_ in solid:
                    node = e.p2d_new_node()
                    if node < 0:
                        self._skipped += 1
                        continue
                    e.p2d_set_pos(node, x + 0.5, lv.height - y - 0.5)
                    e.p2d_add_body(node, BODY_DYNAMIC)
                    e.p2d_add_box(node, 1.0, 1.0)
                    self.actors.append({"node": node, "tile": g_, "w": 1.0, "h": 1.0, "ttl": None, "cell": (x, y)})
        self._build_statics()
        e.p2d_clear_input()
        self.script_report = self._attach_scripts()
        self.playing = True
        self._acc = 0.0
        if self.driver is not None:
            self.driver.start(self)
        self.status = "play: %d solid blocks%s - click drops a ball, B blasts at the pointer%s" % (
            len(self.statics), (", %d beyond the engine's limit skipped" % self._skipped) if self._skipped else "", ("; " + self.script_report) if self.script_report else "")

    def _attach_scripts(self):
        """The project's scripts on their nodes: a sprite's scripts on every tile that shows that sprite (on the crate's own node if the tile is a crate, else on a node of its
        own at the cell), and the game's scripts on one node at the origin. Returns a line for the status: what was attached and what could not be."""
        proj, lv, e = self.project, self.level, self.engine.lib
        ids = self.engine.script_ids
        attached, missing, full = 0, set(), 0
        by_cell = {a["cell"]: a["node"] for a in self.actors if a.get("cell")}

        def attach(node, names):
            nonlocal attached, full
            for name in names:
                if name not in ids:
                    missing.add(name)
                elif e.p2d_attach_script(node, ids[name]):
                    attached += 1
                else:
                    full += 1
        scripted = {k: proj.sprite_for_tile(t) for k, t in proj.tiles.items()}
        scripted = {k: sp.scripts for k, sp in scripted.items() if sp is not None and sp.scripts}
        if scripted:
            for y in range(lv.height):
                for x in range(lv.width):
                    names = scripted.get(self.cells[y * lv.width + x])
                    if not names:
                        continue
                    node = by_cell.get((x, y))
                    if node is None:
                        node = e.p2d_new_node()
                        if node < 0:
                            full += len(names)
                            continue
                        e.p2d_set_pos(node, x + 0.5, lv.height - y - 0.5)
                        self.actors.append({"node": node, "tile": self.cells[y * lv.width + x], "w": 1.0, "h": 1.0, "ttl": None, "cell": (x, y), "script": True})     # (drawn where the script puts it, and gone when it destroys it)
                    attach(node, names)
        if proj.game_scripts:
            node = e.p2d_new_node()
            if node >= 0:
                attach(node, proj.game_scripts)
        parts = []
        if attached:
            parts.append("%d script%s running" % (attached, "" if attached == 1 else "s"))
        if missing:
            parts.append("not in the built library (press Build): " + ", ".join(sorted(missing)))
        if full:
            parts.append("%d not attached (no room: raise [MaxInstances] or the node limit)" % full)
        return "; ".join(parts)

    def _build_statics(self):
        """The solid cells as static boxes, merged into as few rectangles as possible (the scene holds 256 nodes, and a seam between two boxes catches a body that slides
        along it). Called again after a crater has dug cells out."""
        lv, e = self.level, self.engine.lib
        for node in self.statics:
            e.p2d_destroy_node(node)
        self.statics = []
        solid = {k for k, t in self.project.tiles.items() if t.solid and not t.dynamic}
        w_, h_ = lv.width, lv.height
        used = [False] * (w_ * h_)
        for y in range(h_):                              # greedy rectangles: a run along the row, extended down while the rows below have the same run
            x = 0
            while x < w_:
                if self.cells[y * w_ + x] in solid and not used[y * w_ + x]:
                    x0 = x
                    while x < w_ and self.cells[y * w_ + x] in solid and not used[y * w_ + x]:
                        x += 1
                    w = x - x0
                    h = 1
                    while y + h < h_ and all(self.cells[(y + h) * w_ + i] in solid and not used[(y + h) * w_ + i] for i in range(x0, x0 + w)):
                        h += 1
                    for j in range(h):
                        for i in range(x0, x0 + w):
                            used[(y + j) * w_ + i] = True
                    node = e.p2d_new_node()
                    if node < 0:
                        self._skipped += 1
                        continue
                    e.p2d_set_pos(node, x0 + w / 2.0, lv.height - y - h / 2.0)
                    e.p2d_add_body(node, BODY_STATIC)
                    e.p2d_add_box(node, float(w), float(h))
                    self.statics.append(node)
                else:
                    x += 1

    def _stop_play(self):
        if self.playing and self.engine.started:
            self.engine.lib.p2d_clear()
        if self.playing and self.driver is not None:
            self.driver.stop()
        self.playing = False
        self.balls, self.statics, self.actors, self.cells = [], [], [], None

    def blast(self, wx, wy, radius=3.5, force=60.0, dig=None):
        """An explosion in play mode: pushes the bodies near (the engine's AddExplosionForce) and digs the diggable cells within the radius.
        Returns (bodies pushed, cells dug)."""
        lv, e = self.level, self.engine.lib
        if not self.playing or lv is None:
            return 0, 0
        pushed = e.p2d_blast(wx, wy, radius, force)
        dig = radius if dig is None else dig
        diggable = {k for k, t in self.project.tiles.items() if t.diggable}
        dug = 0
        for y in range(lv.height):
            for x in range(lv.width):
                if self.cells[y * lv.width + x] in diggable:
                    dx, dy = x + 0.5 - wx, lv.height - y - 0.5 - wy
                    if dx * dx + dy * dy <= dig * dig:
                        self.cells[y * lv.width + x] = ""
                        dug += 1
        if dug:
            self._build_statics()
        return pushed, dug

    def toggle_play(self):
        if self.playing:
            self._stop_play()
            self.status = "edit view"
        else:
            self._start_play()

    def drop_ball(self, wx, wy):
        e = self.engine.lib
        if len(self.balls) >= 100:
            e.p2d_destroy_node(self.balls.pop(0))
        node = e.p2d_new_node()
        if node >= 0:
            e.p2d_set_pos(node, wx, wy)
            e.p2d_add_body(node, BODY_DYNAMIC)
            e.p2d_add_circle(node, 0.35)
            self.balls.append(node)

    def shatter(self, actor, extra_points=3, speed=4.0):
        """Breaks a movable tile into Voronoi fragments (the engine's Destruction2D): each a rigid body with a polygon collider and a mesh textured with the tile's
        sprite. They fly outward and expire after 2.5 seconds. Returns how many there are."""
        e = self.engine.lib
        x, y = e.p2d_node_x(actor["node"]), e.p2d_node_y(actor["node"])
        self.frag_tile = actor.get("tile") or self.frag_tile
        if actor.get("cell"):
            self.cells[actor["cell"][1] * self.level.width + actor["cell"][0]] = ""
        if actor in self.actors:
            self.actors.remove(actor)
        made = e.p2d_shatter(actor["node"], extra_points, 0)
        for k in range(made):
            node = e.p2d_fragment(k)
            if node < 0:
                continue
            dx, dy = e.p2d_node_x(node) - x, e.p2d_node_y(node) - y
            e.p2d_set_velocity(node, dx * speed * 2 + random.uniform(-1, 1), dy * speed * 2 + random.uniform(1, 4))
            self.actors.append({"node": node, "tile": None, "w": 0.3, "h": 0.3, "ttl": 2.5, "mesh": True})
        return made

    # ---- sand (the CPU's: Engine.cs SandInit ...). The grid covers the level, `scale` cells to a tile; row 0 is the bottom, like the world.
    def sand_dims(self):
        lv = self.level
        if lv is None:
            return None
        scale = max(1, min(int(self.sand.scale), int(math.sqrt(SAND_MAX_CELLS / float(max(1, lv.width * lv.height))))))
        return lv.width * scale, lv.height * scale, scale

    def _sand_ready(self):
        """True if the grid exists for this level and these settings (made now if it has to be); sets sand.error when it cannot be."""
        st, e = self.sand, self.engine
        if not st.enabled or self.level is None or not e.started:
            return False
        dims = self.sand_dims()
        key = (id(self.level), dims, st.generation)
        if key == self._sand_key:
            return True
        w, h, scale = dims
        lib = e.lib
        if not lib.p2d_sand_init(w, h):
            st.error = "the sand grid could not be made (no room for a texture)"
            st.enabled = False
            self._sand_key = None
            return False
        st.error = ""
        lib.p2d_sand_seed(st.seed)
        if st.solid_stone:
            self._sand_stone_from_level(scale)
        self._sand_key, self._sand_dims = key, dims
        return True

    def _sand_stone_from_level(self, scale):
        lv = self.level
        solid = {k for k, t in self.project.tiles.items() if t.solid and not t.dynamic}
        lib = self.engine.lib
        for ty in range(lv.height):
            for tx in range(lv.width):
                if lv.cells[ty * lv.width + tx] in solid:
                    gy0 = (lv.height - 1 - ty) * scale
                    for gy in range(gy0, gy0 + scale):
                        for gx in range(tx * scale, tx * scale + scale):
                            lib.p2d_sand_set(gx, gy, SAND_STONE)

    def sand_cell_at(self, px, py):
        """The grid cell under window pixel (px, py), or None."""
        if self._sand_dims is None:
            return None
        wx, wy = self.screen_to_world(px, py)
        w, h, scale = self._sand_dims
        return int(math.floor(wx * scale)), int(math.floor(wy * scale))

    def sand_paint(self, px, py):
        """The brush at a pixel; from where it was last, when the button is held, so a quick drag leaves no gaps."""
        if not self._sand_ready():
            return
        cell = self.sand_cell_at(px, py)
        if cell is None:
            return
        st, lib = self.sand, self.engine.lib
        a = self._brush_from or cell
        n = max(abs(cell[0] - a[0]), abs(cell[1] - a[1]), 1)
        step = max(1, st.radius)
        for i in range(0, n + 1, step if n > step else 1):
            lib.p2d_sand_brush(a[0] + (cell[0] - a[0]) * i // n, a[1] + (cell[1] - a[1]) * i // n, st.radius, st.element)
        lib.p2d_sand_brush(cell[0], cell[1], st.radius, st.element)
        self._brush_from = cell

    def sand_counts(self):
        """(sand, water, stone) cells in the grid."""
        if self._sand_key is None:
            return 0, 0, 0
        lib = self.engine.lib
        return lib.p2d_sand_count(SAND_SAND), lib.p2d_sand_count(SAND_WATER), lib.p2d_sand_count(SAND_STONE)

    # ---- input
    def _handle_events(self):
        while True:
            ev = self.engine.poll_event()
            if ev is None:
                return
            kind, a, b, c, d = ev
            if kind in (EV_KEY_DOWN, EV_KEY_UP) and self.playing:
                self.engine.lib.p2d_set_key(a, 1 if kind == EV_KEY_DOWN else 0)       # scripts read it with Input2D.Key
            if kind == EV_CLOSE:
                self.closed = True
            elif kind == EV_MOUSE_MOVE:
                self.mouse = (a, b)
                if self._brush_from is not None:
                    self.sand_paint(a, b)
                if self._pan:
                    px, py, cx, cy = self._pan
                    aspect = self.width / float(self.height)
                    self.cx = cx - (a - px) / float(self.width) * 2.0 * self.half * aspect
                    self.cy = cy + (b - py) / float(self.height) * 2.0 * self.half
            elif kind == EV_MOUSE_DOWN:
                self._buttons |= 1 << c
                if c == BTN_LEFT and self.sand.enabled:
                    self._brush_from = None
                    self.sand_paint(a, b)
                elif c == BTN_LEFT and self.playing:
                    self.drop_ball(*self.screen_to_world(a, b))
                elif c in (BTN_RIGHT, BTN_MIDDLE):
                    self._pan = (a, b, self.cx, self.cy)
            elif kind == EV_MOUSE_UP:
                self._buttons &= ~(1 << c)
                if c == BTN_LEFT:
                    self._brush_from = None
                if c in (BTN_RIGHT, BTN_MIDDLE):
                    self._pan = None
            elif kind == EV_WHEEL and d:
                self.half = min(200.0, max(1.5, self.half * (0.9 if d > 0 else 1.0 / 0.9)))
            elif kind == EV_KEY_DOWN:
                step = self.half * 0.1
                if a == ord("P"):
                    self.toggle_play()
                elif a == ord("S"):
                    self.sand.enabled = not self.sand.enabled
                    self.status = "sand on (1 stone, 2 sand, 3 water, 0 erase, [ ] brush, Space pause, C clear)" if self.sand.enabled else "sand off"
                elif self.sand.enabled and a in (ord("0"), ord("1"), ord("2"), ord("3")):
                    self.sand.element = a - ord("0")
                    self.status = "brush: " + SAND_NAMES[self.sand.element]
                elif self.sand.enabled and a in (ord("["), ord("]")):
                    self.sand.radius = max(1, min(40, self.sand.radius + (1 if a == ord("]") else -1)))
                    self.status = "brush radius %d" % self.sand.radius
                elif self.sand.enabled and a == ord(" "):
                    self.sand.paused = not self.sand.paused
                elif self.sand.enabled and a == ord("C"):
                    self.sand.generation += 1
                elif a == ord("B") and self.playing:
                    self.blast(*self.screen_to_world(*self.mouse))
                elif a == ord("R") and self.playing:
                    self._start_play()
                elif a == KEY_HOME:
                    self.fit()
                elif a == KEY_LEFT:
                    self.cx -= step
                elif a == KEY_RIGHT:
                    self.cx += step
                elif a == KEY_UP:
                    self.cy += step
                elif a == KEY_DOWN:
                    self.cy -= step
                elif a == KEY_ESCAPE:
                    self.closed = True

    # ---- a frame
    def tick(self, dt=None):
        """Handles the window's input, advances the animation (and the physics in play mode), draws and presents. Returns False once the window was closed."""
        if not self.is_open:
            return False
        now = time.perf_counter()
        if dt is None:
            dt = 0.0 if self._last is None else min(0.1, now - self._last)
        self._last = now
        self.clock += dt
        self._handle_events()
        if self.closed:
            return False
        e = self.engine.lib
        if self.playing:
            e.p2d_set_mouse(*(self.screen_to_world(*self.mouse) + (self._buttons,)))
            self._acc += dt
            n = 0
            while self._acc >= 1 / 60.0 and n < 4:
                if self.driver is not None:
                    self.driver.step(1 / 60.0)
                e.p2d_step(1 / 60.0)
                for a in [a for a in self.actors if a["ttl"] is not None]:
                    a["ttl"] -= 1 / 60.0
                    if a["ttl"] <= 0:
                        e.p2d_destroy_node(a["node"])
                        self.actors.remove(a)
                self._acc -= 1 / 60.0
                n += 1
        if self.sand.enabled and not self.sand.paused and self._sand_ready():
            e.p2d_sand_step(max(1, int(self.sand.speed)))
        self._draw()
        if not e.gfx_end():                                      # shows the frame in the window; 0 once the window was closed
            self.closed = True
            return False
        return True

    def _apply_lights(self, lv):
        """The level's lights as one scene_lights effect for the camera as it is now, so they stay where they were put."""
        from . import lights
        if lv is None:
            return
        values = lights.effect_values(lv, self.cx, self.cy, self.half, self.width / float(self.height))
        if values is not None:
            self.engine.effect("scene_lights", values)

    def _apply_effects(self, lv):
        """The level's effects, first to last, over everything drawn so far; the disabled ones and any entry the registry no longer accepts draw nothing."""
        for fx in (lv.effects if lv is not None else ()):
            if fx.get("enabled", True):
                try:
                    self.engine.effect(fx["effect"], fx["values"])
                except (KeyError, ValueError):
                    pass

    def _draw(self):
        e = self.engine.lib
        self._sync_textures()
        r, g, b = self.BACKGROUND
        e.gfx_camera(self.cx, self.cy, self.half, r, g, b)
        lv, proj = self.level, self.project
        e.gfx_begin()
        flat = array.array("f")                                  # the sprite batch behind the tiles: the level's frame and tiles with no sprite
        front = array.array("f")                                 # ... and the one in front of them: flat things that move (balls, bullets, a blast's flash)
        quads = {}                                               # texture id -> array of mesh vertices: the tiles
        aquads = {}                                              # ... and the movable things, drawn over the tiles
        if proj.backdrop:
            scenery.draw(proj.backdrop, self, flat)
        if lv is not None:
            aspect = self.width / float(self.height)
            x0 = max(0, int(self.cx - self.half * aspect) - 1)
            x1 = min(lv.width, int(self.cx + self.half * aspect) + 2)
            y0 = max(0, int(lv.height - (self.cy + self.half)) - 1)
            y1 = min(lv.height, int(lv.height - (self.cy - self.half)) + 2)
            sprite_cache = {}
            cells = self.cells if self.playing else lv.cells
            hidden = {a["cell"] for a in self.actors if a.get("cell")} if self.playing else ()
            for y in range(y0, y1):
                for x in range(x0, x1):
                    g_ = cells[y * lv.width + x]
                    if not g_ or (x, y) in hidden:
                        continue
                    tile = proj.tiles.get(g_)
                    spr = None
                    if tile is not None:
                        if g_ not in sprite_cache:
                            sprite_cache[g_] = proj.sprite_for_tile(tile)
                        spr = sprite_cache[g_]
                    cx, cy = x + 0.5, lv.height - y - 0.5
                    tex = 0
                    if spr is not None:
                        frame = int(self.clock * spr.fps) % len(spr.frames) if len(spr.frames) > 1 and spr.fps > 0 else 0
                        tex = self._texture(spr, frame)
                    if tex:
                        v = quads.setdefault(tex, array.array("f"))
                        l, rr, t, bt = cx - 0.5, cx + 0.5, cy + 0.5, cy - 0.5
                        v.extend((l, t, 0, 0, 1, 1, 1, 1, rr, t, 1, 0, 1, 1, 1, 1, rr, bt, 1, 1, 1, 1, 1, 1,
                                  l, t, 0, 0, 1, 1, 1, 1, rr, bt, 1, 1, 1, 1, 1, 1, l, bt, 0, 1, 1, 1, 1, 1))
                    else:
                        pr, pg, pb = placeholder_color(g_)
                        flat.extend((cx, cy, 0.5, 0.5, 0.0, pr, pg, pb, 1.0, 0, 1, 0))      # layer 1: over the frame
            # a faint frame around the level (layer 0, under the tiles), so its edge shows against the background
            if not proj.backdrop:
                flat.extend((lv.width / 2.0, lv.height / 2.0, lv.width / 2.0 + 0.06, lv.height / 2.0 + 0.06, 0.0, 0.2, 0.22, 0.3, 1.0, 0, 0, 0))
        if self.playing:
            for a in [a for a in self.actors if a.get("script") and not self.engine.lib.p2d_node_alive(a["node"])]:
                self.actors.remove(a)                            # a script destroyed its node (a gem was picked up): the tile is gone with it
                self.cells[a["cell"][1] * self.level.width + a["cell"][0]] = ""
            for a in self.actors:
                if a.get("script") and not self.engine.lib.p2d_node_active(a["node"]):
                    continue                                     # a script switched it off (a crumbled platform)
                nx, ny, ang = self.engine.lib.p2d_node_x(a["node"]), self.engine.lib.p2d_node_y(a["node"]) + a.get("dy", 0.0), self.engine.lib.p2d_node_angle(a["node"])
                spr = proj.sprite_for_tile(proj.tiles[a["tile"]]) if a.get("tile") in proj.tiles else None
                tex = 0
                if spr is not None:
                    frame = int(self.clock * spr.fps) % len(spr.frames) if len(spr.frames) > 1 and spr.fps > 0 else 0
                    if a.get("frame") is not None:
                        frame = a["frame"] % len(spr.frames)
                    tex = self._texture(spr, frame)
                if a.get("mesh"):
                    continue                                     # a fragment: the scene draws it (p2d_draw_meshes)
                if tex:
                    hw, hh = a["w"] / 2.0 * a.get("flip", 1.0), a["h"] / 2.0
                    ca, sa = math.cos(ang), math.sin(ang)
                    pts = [(nx + ca * px - sa * py, ny + sa * px + ca * py) for px, py in ((-hw, hh), (hw, hh), (hw, -hh), (-hw, -hh))]
                    uv = ((0, 0), (1, 0), (1, 1), (0, 1))
                    v = aquads.setdefault(tex, array.array("f"))
                    for i in (0, 1, 2, 0, 2, 3):
                        v.extend((pts[i][0], pts[i][1], uv[i][0], uv[i][1], 1, 1, 1, 1))
                else:
                    r, g, b = a.get("color", (0.8, 0.55, 0.3))
                    front.extend((nx, ny, a["w"] / 2.0, a["h"] / 2.0, ang, r, g, b, a.get("alpha", 1.0), a.get("shape", 0), a.get("layer", 2), 0))
        if self.playing:                                         # what scripts made and gave a sprite (add_sprite): bullets, arrows, a rope
            lib, known = self.engine.lib, {a["node"] for a in self.actors}
            known.update(self.balls)
            for node in range(lib.p2d_node_slots()):
                if node in known or not lib.p2d_node_alive(node) or not lib.p2d_node_active(node):
                    continue
                shape = lib.p2d_sprite_info(node, 0)
                if shape < 0:
                    continue
                front.extend((lib.p2d_node_x(node), lib.p2d_node_y(node), lib.p2d_sprite_info(node, 1) / 2.0, lib.p2d_sprite_info(node, 2) / 2.0, lib.p2d_node_angle(node),
                             lib.p2d_sprite_info(node, 3), lib.p2d_sprite_info(node, 4), lib.p2d_sprite_info(node, 5), lib.p2d_sprite_info(node, 6), int(shape), 4, 0))
        for node in self.balls:
            front.extend((self.engine.lib.p2d_node_x(node), self.engine.lib.p2d_node_y(node), 0.35, 0.35, 0.0, 1.0, 0.55, 0.2, 1.0, 1, 5, 0))
        if flat:
            e.gfx_sprites(floats_ptr(flat), len(flat) // 12)
        for group in (quads, aquads):
            for tex, verts in group.items():
                e.gfx_triangles(floats_ptr(verts), len(verts) // 8, tex)
        if self.playing and any(a.get("mesh") for a in self.actors):    # the shattered crates' fragments, textured with the crate's picture
            spr = self.project.sprite_for_tile(self.project.tiles[self.frag_tile]) if self.frag_tile in self.project.tiles else None
            e.p2d_draw_meshes(self._texture(spr, 0) if spr is not None else 0)
        if front:
            e.gfx_sprites(floats_ptr(front), len(front) // 12)
        if lv is not None and self.sand.enabled and self._sand_ready():
            e.p2d_sand_draw(0.0, 0.0, float(lv.width), float(lv.height))
        self._apply_lights(lv)
        self._apply_effects(lv)


"""Tests of the engine as Python sees it: libstride2d.so through ctypes (the C# runtime translated to C, with Box2D and the renderer).

The engine API tests need only the library (the renderer draws offscreen, or on the CPU, without a display); the viewport tests also need a display (xvfb-run python3 -m unittest ...) and are skipped
without one. Everything is skipped, with the reason, if the library is not built:  python3 build.py so
"""
import array
import os
import unittest

from .demo import make_demo_project
from .slime_demo import SlimeDriver, make_slime_project
from .slime_rust import make_slime_rust_project
from . import scriptbuild
from .engine import (BODY_DYNAMIC, BODY_STATIC, BTN_LEFT, EV_MOUSE_DOWN, EV_WHEEL, KEY_HOME, Engine, EngineError, Viewport, find_library, floats_ptr)

W, H = 800, 480           # the renderer's picture is made once per process, at the size it is first started with
_engine = None


def setUpModule():
    global _engine
    if find_library() is None:
        raise unittest.SkipTest("libstride2d.so is not built (python3 build.py so)")
    try:
        _engine = Engine()
        _engine.start(W, H)
    except EngineError as e:
        raise unittest.SkipTest(str(e))


def tearDownModule():
    if _engine is not None:
        _engine.stop()


def ensure_started():
    """A viewport that is closed shuts the renderer down with its window; the next test starts it again (the scene, an arena of one, is reused)."""
    _engine.start(W, H)


def rgb(v):
    return ((v >> 16) & 255, (v >> 8) & 255, v & 255)


class EngineApi(unittest.TestCase):
    def setUp(self):
        ensure_started()
        self.e = _engine.lib
        self.e.p2d_clear()

    def draw(self):
        """One frame of the scene's sprites: begin, the engine's sprites, end (which shows it in the window, if there is one)."""
        e = self.e
        e.gfx_begin()
        n = e.p2d_draw_sprites()
        e.gfx_end()
        return n

    def test_version_and_the_exports_the_header_promises(self):
        self.assertEqual(self.e.p2d_version(), 8)
        header = os.path.join(os.path.dirname(_engine.path), "libstride2d.h")
        if os.path.exists(header):
            import re
            with open(header) as f:
                names = re.findall(r"\bp2d_\w+(?=\()", f.read())
            self.assertTrue(len(names) >= 20)
            for n in names:
                self.assertTrue(hasattr(self.e, n), n)

    def test_a_dynamic_ball_falls_and_rests_on_a_static_box(self):
        e = self.e
        ground = e.p2d_new_node()
        e.p2d_set_pos(ground, 0.0, -0.5)
        self.assertEqual(e.p2d_add_body(ground, BODY_STATIC), 1)
        self.assertEqual(e.p2d_add_box(ground, 20.0, 1.0), 1)
        ball = e.p2d_new_node()
        e.p2d_set_pos(ball, 0.0, 5.0)
        e.p2d_add_body(ball, BODY_DYNAMIC)
        e.p2d_add_circle(ball, 0.5)
        self.assertAlmostEqual(e.p2d_node_y(ball), 5.0, places=3)
        for _ in range(30):
            e.p2d_step(1 / 60.0)
        mid = e.p2d_node_y(ball)
        self.assertTrue(0.5 < mid < 5.0, mid)                           # half a second in: still falling
        for _ in range(240):
            e.p2d_step(1 / 60.0)
        self.assertAlmostEqual(e.p2d_node_y(ball), 0.5, delta=0.02)    # at rest on the box's top (y = 0), radius 0.5
        self.assertAlmostEqual(e.p2d_node_x(ball), 0.0, delta=0.01)

    def test_velocity_impulse_and_blast_move_bodies(self):
        e = self.e
        e.p2d_gravity(0.0, 0.0)
        a = e.p2d_new_node()
        e.p2d_set_pos(a, 0.0, 0.0)
        e.p2d_add_body(a, BODY_DYNAMIC)
        e.p2d_add_box(a, 1.0, 1.0)
        e.p2d_set_velocity(a, 3.0, 0.0)
        e.p2d_step(1 / 60.0)
        self.assertAlmostEqual(e.p2d_velocity_x(a), 3.0, delta=0.05)
        e.p2d_set_velocity(a, 0.0, 0.0)
        e.p2d_impulse(a, 0.0, 5.0)
        e.p2d_step(1 / 60.0)
        self.assertGreater(e.p2d_velocity_y(a), 0.5)
        e.p2d_set_velocity(a, 0.0, 0.0)
        e.p2d_set_pos(a, 1.0, 0.0)
        e.p2d_step(1 / 60.0)
        self.assertEqual(e.p2d_blast(0.0, 0.0, 3.0, 60.0), 1)
        e.p2d_step(1 / 60.0)
        self.assertGreater(e.p2d_velocity_x(a), 0.0)                       # pushed away from the blast
        self.assertEqual(e.p2d_velocity_x(-1), 0.0)
        e.p2d_set_velocity(300, 1.0, 1.0)                                  # harmless

    def test_clear_and_the_node_limit(self):
        e = self.e
        made = 0
        while e.p2d_new_node() >= 0:
            made += 1
            self.assertLessEqual(made, 1000)
        self.assertEqual(e.p2d_node_count(), made)
        self.assertEqual(made, 256)                                     # CoreLimits.Nodes: refused cleanly (-1), not a crash
        e.p2d_clear()
        self.assertEqual(e.p2d_node_count(), 0)
        self.assertGreaterEqual(e.p2d_new_node(), 0)                    # the slots came back

    def test_a_node_index_that_is_not_a_node_is_harmless(self):
        e = self.e
        e.p2d_set_pos(200, 1.0, 1.0)
        e.p2d_destroy_node(-1)
        self.assertEqual(e.p2d_node_x(255), 0.0)
        self.assertEqual(e.p2d_add_sprite(255, 0, 1.0, 1.0, 1.0, 1.0, 1.0), 0)

    def test_draw_the_scenes_sprites(self):
        e = self.e
        e.p2d_camera(0.0, 0.0, 4.0, 0.0, 0.0, 0.0)
        n = e.p2d_new_node()
        e.p2d_add_sprite(n, 0, 2.0, 2.0, 1.0, 0.0, 0.0)                 # a red box in the middle
        self.assertEqual(self.draw(), 1)
        self.assertEqual(rgb(e.gfx_pixel(W // 2, H // 2)), (255, 0, 0))
        self.assertEqual(rgb(e.gfx_pixel(2, 2)), (0, 0, 0))             # the background
        e.p2d_set_pos(n, 100.0, 0.0)                                    # off screen
        self.draw()
        self.assertEqual(rgb(e.gfx_pixel(W // 2, H // 2)), (0, 0, 0))

    def test_textures_and_triangles_from_python(self):
        import array
        import ctypes as C
        e = self.e
        e.p2d_camera(0.0, 0.0, 4.0, 0.0, 0.0, 0.0)
        pix = (C.c_uint8 * 16)(0, 255, 0, 255, 0, 255, 0, 255, 0, 255, 0, 255, 0, 255, 0, 255)       # a 2x2 green texture
        tex = e.gfx_texture(2, 2, 0, C.addressof(pix))
        self.assertGreater(tex, 0)
        e.gfx_begin()
        quad = array.array("f", [-1, 1, 0, 0, 1, 1, 1, 1, 1, 1, 1, 0, 1, 1, 1, 1, 1, -1, 1, 1, 1, 1, 1, 1,
                                 -1, 1, 0, 0, 1, 1, 1, 1, 1, -1, 1, 1, 1, 1, 1, 1, -1, -1, 0, 1, 1, 1, 1, 1])
        self.assertEqual(e.gfx_triangles(quad.buffer_info()[0], 6, tex), 6)
        e.gfx_end()
        self.assertEqual(rgb(e.gfx_pixel(W // 2, H // 2)), (0, 255, 0))
        e.gfx_texture_free(tex)

    def test_a_node_shatters_into_fragments_that_are_bodies_and_meshes(self):
        e = self.e
        e.p2d_gravity(0.0, 0.0)
        crate = e.p2d_new_node()
        e.p2d_set_pos(crate, 0.0, 0.0)
        e.p2d_add_body(crate, BODY_DYNAMIC)
        e.p2d_add_box(crate, 1.0, 1.0)
        made = e.p2d_shatter(crate, 3, 0)
        self.assertGreaterEqual(made, 4)
        frags = [e.p2d_fragment(k) for k in range(made)]
        self.assertTrue(all(f >= 0 for f in frags))
        self.assertEqual(e.p2d_fragment(made), -1)
        e.p2d_set_velocity(frags[0], 2.0, 0.0)                                # a fragment is a body like any other
        e.p2d_step(1 / 60.0)
        self.assertGreater(e.p2d_velocity_x(frags[0]), 1.0)
        e.p2d_camera(0.0, 0.0, 2.0, 0.0, 0.0, 0.0)
        e.gfx_begin()
        self.assertGreaterEqual(e.p2d_draw_meshes(0), made * 3)                # drawn as triangles
        e.gfx_end()
        self.assertEqual(e.p2d_shatter(-1, 3, 0), 0)                          # not a node: refused

    def test_events_can_be_injected_and_polled(self):
        e = self.e
        while _engine.poll_event():
            pass
        self.assertEqual(e.gfx_inject_event(EV_WHEEL, 10, 20, 0, 120), 1)
        self.assertEqual(_engine.poll_event(), (EV_WHEEL, 10, 20, 0, 120))
        self.assertIsNone(_engine.poll_event())


class Effects(unittest.TestCase):
    """gfx_effect through Engine.effect: an effect changes the picture drawn before it, inside the clip, and nothing drawn after it."""

    def setUp(self):
        ensure_started()
        self.e = _engine.lib

    def box(self, x, grey):
        """A square 4 world units wide, centred at (x, 0), of one grey (the camera below shows 10 units over the picture's height: 48 pixels to the unit)."""
        return array.array("f", [x, 0.0, 2.0, 2.0, 0.0, grey, grey, grey, 1.0, 0.0, 0.0, 0.0])

    def pixel(self, wx):
        return rgb(self.e.gfx_pixel(int(W / 2 + wx * (H / 10.0)), H // 2))

    def test_an_effect_changes_what_was_drawn_before_it_and_not_what_comes_after(self):
        e = self.e
        e.gfx_camera(0.0, 0.0, 5.0, 0.0, 0.0, 0.0)
        e.gfx_begin()
        before, after = self.box(-4.0, 0.2), self.box(4.0, 0.2)
        e.gfx_sprites(floats_ptr(before), 1)
        self.assertTrue(_engine.effect("bright_contrast", {"brightness": 0.3}))
        e.gfx_sprites(floats_ptr(after), 1)
        e.gfx_end()
        for got, want in zip(self.pixel(-4.0), (128, 128, 128)):          # 0.2 + 0.3 = 0.5
            self.assertAlmostEqual(got, want, delta=2)
        for got, want in zip(self.pixel(4.0), (51, 51, 51)):              # drawn after the effect: 0.2 as it was
            self.assertAlmostEqual(got, want, delta=1)
        for got, want in zip(rgb(e.gfx_pixel(5, H - 5)), (77, 77, 77)):   # the background, black, is brightened as well
            self.assertAlmostEqual(got, want, delta=2)

    def test_an_effect_stays_inside_the_clip(self):
        e = self.e
        e.gfx_camera(0.0, 0.0, 5.0, 0.0, 0.0, 0.0)
        e.gfx_begin()
        b = self.box(0.0, 0.2)
        e.gfx_sprites(floats_ptr(b), 1)
        e.gfx_clip(W // 2, 0, W // 2, H)                                   # the right half only
        _engine.effect("bright_contrast", {"brightness": 0.3})
        e.gfx_clip_reset()
        e.gfx_end()
        left, right = rgb(e.gfx_pixel(W // 2 - 20, H // 2)), rgb(e.gfx_pixel(W // 2 + 20, H // 2))
        for got, want in zip(left, (51, 51, 51)):
            self.assertAlmostEqual(got, want, delta=1)
        for got, want in zip(right, (128, 128, 128)):
            self.assertAlmostEqual(got, want, delta=2)

    def test_what_the_api_refuses(self):
        self.assertEqual(self.e.gfx_effect(999, None, 0), 0)
        self.assertEqual(self.e.gfx_effect(0, None, 0), 0)
        with self.assertRaises(KeyError):
            _engine.effect("no_such_effect")


@unittest.skipUnless(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"), "needs a display (run under xvfb-run)")
class ViewportWindow(unittest.TestCase):
    def setUp(self):
        ensure_started()
        self.project = make_demo_project()
        self.vp = Viewport(_engine, self.project, W, H)
        self.vp.show_level(self.project.levels[0])
        try:
            self.vp.open()
        except EngineError as e:
            self.skipTest(str(e))
        self.lib = _engine.lib

    def tearDown(self):
        self.vp.close()

    def cell_px(self, col, row):
        vp = self.vp
        wx, wy = col + 0.5, vp.level.height - row - 0.5
        return (int((wx - vp.cx) / (2 * vp.half * (W / H)) * W + W / 2), int(H / 2 - (wy - vp.cy) / (2 * vp.half) * H))

    def test_the_level_is_drawn_where_its_cells_are(self):
        self.assertTrue(self.vp.is_open)
        self.vp.tick(0.0)
        brick = rgb(self.lib.gfx_pixel(*self.cell_px(9, 4)))
        self.assertEqual(brick, (224, 60, 60))                                  # the brick sprite's red
        outside = rgb(self.lib.gfx_pixel(5, 5))
        self.assertEqual(outside, tuple(int(round(c * 255)) for c in self.vp.BACKGROUND))

    def test_the_coin_animates_and_the_palette_recolours_it(self):
        self.vp.tick(0.0)
        h0 = self.lib.gfx_frame_hash()
        for _ in range(8):
            self.vp.tick(0.05)
        self.assertNotEqual(h0, self.lib.gfx_frame_hash())                      # frames of the spinning coin
        self.vp.tick(0.0)
        before = self.lib.gfx_frame_hash()
        self.project.palette.set_color(self.project.palette.index_of("R"), (0, 0, 255))     # the bricks' index changes colour...
        self.project.touch()                                                    # ...and the viewport notices the edit
        self.vp.tick(0.0)
        self.assertNotEqual(before, self.lib.gfx_frame_hash())
        self.assertEqual(rgb(self.lib.gfx_pixel(*self.cell_px(9, 4))), (0, 0, 255))

    def test_wheel_zoom_and_home_arrive_through_the_windows_event_queue(self):
        half = self.vp.half
        self.lib.gfx_inject_event(EV_WHEEL, W // 2, H // 2, 0, 120)
        self.vp.tick(0.0)
        self.assertLess(self.vp.half, half)
        self.lib.gfx_inject_event(5, KEY_HOME, 0, 0, 0)
        self.vp.tick(0.0)
        self.assertAlmostEqual(self.vp.half, half, places=6)

    def test_play_mode_a_click_drops_a_ball_that_lands_on_the_bricks(self):
        self.vp.toggle_play()
        self.assertTrue(self.vp.playing)
        wx, wy = 12.0, 9.0                                                     # above the top brick platform (its top edge is y = 8)
        px = int((wx - self.vp.cx) / (2 * self.vp.half * (W / H)) * W + W / 2)
        py = int(H / 2 - (wy - self.vp.cy) / (2 * self.vp.half) * H)
        self.lib.gfx_inject_event(EV_MOUSE_DOWN, px, py, BTN_LEFT, 0)
        self.vp.tick(0.0)
        self.assertEqual(len(self.vp.balls), 1)
        for _ in range(240):
            self.vp.tick(1 / 60.0)
        self.assertAlmostEqual(self.lib.p2d_node_y(self.vp.balls[0]), 8.0 + 0.35, delta=0.03)
        self.vp.toggle_play()
        self.assertEqual(self.lib.p2d_node_count(), 0)                          # leaving play mode clears the scene

    def test_closing_the_window_ends_the_ticks(self):
        self.lib.gfx_inject_event(9, 0, 0, 0, 0)                                # GFX_EVENT_CLOSE, as the window's close button sends it
        self.assertFalse(self.vp.tick(0.0))
        self.assertTrue(self.vp.closed)


@unittest.skipUnless(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"), "needs a display (run under xvfb-run)")
class SandInTheViewport(unittest.TestCase):
    """The CPU sand in the viewport: painted with the mouse, falls, stops at the level's solid tiles, and is drawn."""

    cell_px = ViewportWindow.cell_px

    def setUp(self):
        self.project = make_demo_project()
        self.vp = Viewport(_engine, self.project, W, H)
        self.vp.show_level(self.project.levels[0])
        try:
            self.vp.open()
        except EngineError as e:
            self.skipTest(str(e))
        self.lib = _engine.lib
        self.vp.sand.enabled = True
        self.vp.sand.element = 2
        self.vp.sand.radius = 3
        self.vp.fit()
        self.vp.tick(0.0)
        if not self.vp.sand.enabled:
            self.skipTest(self.vp.sand.error)

    def tearDown(self):
        self.vp.close()

    def paint_at_tile(self, col, row, held=1):
        from .engine import EV_MOUSE_UP
        x, y = self.cell_px(col, row)
        self.lib.gfx_inject_event(EV_MOUSE_DOWN, x, y, BTN_LEFT, 0)
        for _ in range(held):
            self.vp.tick(0.0)
        self.lib.gfx_inject_event(EV_MOUSE_UP, x, y, BTN_LEFT, 0)
        self.vp.tick(0.0)

    def test_the_stone_of_the_level_is_in_the_grid(self):
        sand, water, stone = self.vp.sand_counts()
        solid = {k for k, t in self.project.tiles.items() if t.solid and not t.dynamic}
        lv = self.vp.level
        tiles = sum(1 for c in lv.cells if c in solid)
        self.assertGreater(tiles, 0)
        self.assertEqual(stone, tiles * self.vp.sand_dims()[2] ** 2)
        self.assertEqual((sand, water), (0, 0))

    def test_the_mouse_paints_the_chosen_element_and_nothing_is_lost_as_it_falls(self):
        self.vp.sand.element = 3
        self.paint_at_tile(8, 1)
        _, water, _ = self.vp.sand_counts()
        self.assertGreater(water, 10)
        for _ in range(120):
            self.vp.tick(0.0)
        self.assertEqual(self.vp.sand_counts()[1], water)                      # water falls and spreads; it is not made or lost

    def test_it_is_drawn_and_the_pause_stops_it(self):
        self.paint_at_tile(8, 1)
        h = self.lib.gfx_frame_hash()
        self.vp.tick(0.0)
        self.assertNotEqual(h, self.lib.gfx_frame_hash())                      # a falling pile changes the picture
        for _ in range(400):
            self.vp.tick(0.0)
        self.vp.sand.paused = True
        self.vp.tick(0.0)
        h = self.lib.gfx_frame_hash()
        self.vp.tick(0.0)
        self.assertEqual(h, self.lib.gfx_frame_hash())

    def test_keys_pick_the_element_and_c_clears_the_grid(self):
        from .engine import EV_KEY_DOWN
        self.lib.gfx_inject_event(EV_KEY_DOWN, ord("3"), 0, 0, 0)
        self.vp.tick(0.0)
        self.assertEqual(self.vp.sand.element, 3)
        self.paint_at_tile(8, 1)
        self.assertGreater(self.vp.sand_counts()[1], 0)
        self.lib.gfx_inject_event(EV_KEY_DOWN, ord("C"), 0, 0, 0)
        self.vp.tick(0.0)
        self.assertEqual(self.vp.sand_counts()[1], 0)

    def test_the_same_painting_gives_the_same_grid(self):
        self.paint_at_tile(8, 1)
        for _ in range(60):
            self.vp.tick(0.0)
        first = self.lib.p2d_sand_hash()
        self.vp.sand.generation += 1
        self.vp.tick(0.0)
        self.paint_at_tile(8, 1)
        for _ in range(60):
            self.vp.tick(0.0)
        self.assertEqual(first, self.lib.p2d_sand_hash())


@unittest.skipUnless(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"), "needs a display (run under xvfb-run)")
class SlimeJumpDestructInTheViewport(unittest.TestCase):
    def test_the_slime_digs_craters_bursts_the_worm_and_reaches_the_goal(self):
        ensure_started()
        project = make_slime_project()
        vp = Viewport(_engine, project, W, H)
        vp.show_level(project.levels[0])
        vp.driver = SlimeDriver()
        try:
            vp.open()
        except EngineError as e:
            self.skipTest(str(e))
        try:
            vp.toggle_play()
            lv = vp.level
            dirt = "\U0001f7eb"
            dirt_before = lv.cells.count(dirt)
            self.assertEqual(sum(1 for c in vp.cells if c == "\U0001fab1"), 1)       # a worm
            for _ in range(60 * 30):
                if not vp.tick(1 / 60.0) or vp.driver.done:
                    break
            d = vp.driver
            self.assertTrue(d.won, d.log)
            self.assertTrue(any(l.startswith("worm burst") for l in d.log), d.log)     # the worm was shot and shattered
            self.assertTrue(any(l.startswith("crater") for l in d.log), d.log)         # a bullet dug the ground
            self.assertLess(vp.cells.count(dirt), dirt_before)
            self.assertEqual(lv.cells.count(dirt), dirt_before)                        # ...in the play copy only: the level is as it was
            self.assertFalse(project.dirty)                                            # and playing (the blinking eyes) is not an edit
        finally:
            vp.close()


class SlimeJumpInRust(unittest.TestCase):
    """SlimeJump (slime_rust.py): its game logic is the Rust scripts of samples/SlimeJumpRust (walking, climbing, the blaster and the lasso, turrets and arrows, crumbly platforms,
    checkpoints, gems, and a bot), built into the engine by the editor's own Build and played in the viewport. The level is 84 x 16 cells; the ground is at y = 4."""
    SPAWN = (3.5, 4.4)

    @classmethod
    def setUpClass(cls):
        if find_library() is None:
            raise unittest.SkipTest("libstride2d.so is not built (python3 tools/engine_so.py)")
        import tempfile
        cls.work = tempfile.TemporaryDirectory()
        cls.project = make_slime_rust_project()
        cls.result = scriptbuild.Builder(cls.work.name).build(cls.project)
        if not cls.result.ok:
            raise AssertionError("the Rust scripts did not build: " + "; ".join(str(d) for d in cls.result.diagnostics))
        try:
            cls.engine = Engine(cls.result.lib)
            cls.engine.start(W, H)
        except EngineError as e:
            raise unittest.SkipTest(str(e))

    @classmethod
    def tearDownClass(cls):
        # (the engine is not stopped: shutting a second copy of the library down takes the process's EGL display with it, and the other classes' engine draws on it)
        if getattr(cls, "work", None) is not None:
            cls.work.cleanup()

    def setUp(self):
        self.vp = Viewport(self.engine, self.project, W, H)
        self.vp.show_level(self.project.levels[0])
        try:
            self.vp.open()
        except EngineError as e:
            self.skipTest(str(e))
        self.vp.toggle_play()
        self.lib = self.engine.lib
        self.tick(30)                                                                  # (the slime lands)
        self.slime = self.node_with_tag(1)
        self.assertIsNotNone(self.slime)

    def tearDown(self):
        self.lib.p2d_clear_input()
        self.aim(0.0, 0.0, 0)
        self.vp.close()

    def tick(self, n=1):
        for _ in range(n):
            self.vp.tick(1 / 60.0)

    def node_with_tag(self, tag):
        return next((n for n in range(self.lib.p2d_node_slots()) if self.lib.p2d_get_tag(n) == tag), None)

    def worm_near(self, x):
        """The worm (tag 2) that crawls about x."""
        lib = self.lib
        return next((n for n in range(lib.p2d_node_slots()) if lib.p2d_get_tag(n) == 2 and abs(lib.p2d_node_x(n) - x) < 4.0), None)

    def aim(self, x, y, buttons=0):
        """Where the mouse is (a world point) and which buttons are held (bit 0 left, 2 right)."""
        self.vp.screen_to_world = lambda px, py: (x, y)
        self.vp._buttons = buttons

    def glob(self, i):
        return self.lib.p2d_get_global(i)

    def node_at(self, x, y, reach=0.6):
        """The node of the cell centred at (x, y) (reach: how far from it it may be, for a worm that crawls)."""
        lib = self.lib
        return next((n for n in range(lib.p2d_node_slots()) if lib.p2d_node_alive(n) and abs(lib.p2d_node_x(n) - x) < reach and abs(lib.p2d_node_y(n) - y) < 0.6 and n != self.slime), None)

    def pos(self, n=None):
        n = self.slime if n is None else n
        return self.lib.p2d_node_x(n), self.lib.p2d_node_y(n)

    def teleport(self, x, y, vx=0.0, vy=0.0):
        self.lib.p2d_set_pos(self.slime, x, y)
        self.lib.p2d_set_velocity(self.slime, vx, vy)

    def assertAtStart(self):
        x, y = self.pos()
        self.assertAlmostEqual(x, self.SPAWN[0], 1)
        self.assertLess(abs(y - self.SPAWN[1]), 0.5)
        self.assertEqual(self.lib.p2d_get_tag(self.slime), 1)                          # (and well again)

    def test_the_rust_scripts_were_built_and_attached(self):
        self.assertEqual(sorted(self.result.scripts), sorted(("Slime", "Worm", "Spikes", "Gem", "Goal", "Bullet", "Arrow", "Turret", "Crumbly", "Vine", "Anchor", "Save", "Bot")))
        self.assertEqual(self.result.diagnostics, [])
        self.assertIn("32 scripts running", self.vp.script_report)
        x, y = self.pos()
        self.assertAlmostEqual(x, self.SPAWN[0], 1)
        self.assertAlmostEqual(y, self.SPAWN[1], 1)                                    # it stands on the ground

    def test_the_slime_walks_and_jumps_as_high_as_the_key_is_held(self):
        lib = self.lib
        lib.p2d_set_key(262, 1)                                                        # right arrow
        self.tick(30)
        self.assertGreater(self.pos()[0], self.SPAWN[0] + 3.0)
        lib.p2d_set_key(262, 0)
        lib.p2d_set_key(65, 1)                                                         # A: left
        self.tick(30)
        lib.p2d_set_key(65, 0)
        self.assertLess(self.pos()[0], self.SPAWN[0] + 2.0)
        apex = {}
        for name, frames in (("full", 40), ("hop", 3)):
            self.teleport(self.SPAWN[0], self.SPAWN[1])
            self.tick(60)
            lib.p2d_set_key(32, 1)
            top = 0.0
            for i in range(60):
                self.tick(1)
                if i == frames:
                    lib.p2d_set_key(32, 0)
                top = max(top, self.pos()[1] - self.SPAWN[1])
            lib.p2d_set_key(32, 0)
            apex[name] = top
        self.assertGreater(apex["full"], 3.5)
        self.assertLess(apex["hop"], apex["full"] - 1.0)                               # let go early and it is a hop
        self.assertLess(apex["full"], 5.0)                                             # (and no second jump in the air)

    def test_spikes_a_fall_and_a_worm_from_the_side_send_it_back_to_the_start(self):
        self.teleport(7.5, 4.5)                                                        # on the spikes
        self.tick(5)
        self.assertAtStart()
        self.teleport(21.5, 6.0)                                                       # over the pit
        self.tick(150)
        self.assertAtStart()
        worm = self.worm_near(15.5)
        self.assertIsNotNone(worm)
        wx, wy = self.pos(worm)
        self.teleport(wx - 0.6, wy + 0.1)                                              # beside the worm
        self.tick(5)
        self.assertAtStart()
        self.assertEqual(self.lib.p2d_node_alive(worm), 1)                             # (it is not hurt by that)
        self.assertEqual(self.glob(0), 3)                                              # three deaths so far

    def test_a_slime_that_lands_on_a_worm_squashes_it_and_bounces(self):
        worm = self.worm_near(15.5)
        wx, wy = self.pos(worm)
        self.teleport(wx, wy + 1.1, 0.0, -4.0)
        top = -1e9
        for _ in range(20):
            self.tick(1)
            top = max(top, self.pos()[1])
        self.assertEqual(self.lib.p2d_node_alive(worm), 0)
        self.assertGreater(top, wy + 1.5)
        self.assertEqual(self.lib.p2d_get_tag(self.slime), 1)

    def test_a_gem_is_picked_up_and_kept_at_the_next_checkpoint_or_back_if_the_slime_dies_first(self):
        self.lib.p2d_destroy_node(self.worm_near(15.5))                                # (the worm would hurt it by the gem)
        gem = self.node_at(16.5, 4.5)
        self.assertIsNotNone(gem)
        self.teleport(16.5, 4.5)
        self.tick(3)
        self.assertLess(self.pos(gem)[1], -50)                                         # gone from the level (far below it)
        self.assertEqual(self.glob(4), 1)
        self.teleport(7.5, 4.5)                                                        # dies on the spikes: the gem is back
        self.tick(5)
        self.assertGreater(self.pos(gem)[1], 0)
        self.assertEqual(self.glob(4), 0)
        self.teleport(16.5, 4.5)
        self.tick(3)
        self.assertEqual(self.glob(4), 1)
        self.teleport(26.5, 4.5)                                                       # a checkpoint: kept
        self.tick(5)
        self.assertEqual(self.glob(1), 1)
        self.tick(40)                                                                  # (a respawn pause is over)
        self.teleport(7.5, 4.5)
        self.tick(5)
        self.assertLess(self.pos(gem)[1], -50)
        self.assertEqual(self.glob(4), 1)
        x, y = self.pos()
        self.assertAlmostEqual(x, 26.5, 1)                                             # and it starts again from the checkpoint

    def test_climbing_the_vines_up_the_wall(self):
        lib = self.lib
        lib.p2d_destroy_node(self.node_at(47.5, 4.5))                                  # (the turret, which would shoot it)
        self.teleport(50.5, 4.4)
        lib.p2d_set_key(262, 1)                                                        # right, up to the wall, and jump (climb)
        lib.p2d_set_key(32, 1)
        top = 0.0
        for _ in range(120):
            self.tick(1)
            top = max(top, self.pos()[1])
            if self.glob(16) > 0.5:
                break
        self.assertEqual(self.glob(16), 1)                                             # climbing
        for _ in range(120):
            self.tick(1)
            top = max(top, self.pos()[1])
        self.assertGreater(top, 12.0)                                                  # it went up the whole wall (eight units) ...
        self.assertGreater(self.pos()[0], 52.0)                                        # ... and over the lip

    def test_the_blaster_shoots_a_worm(self):
        worm = self.worm_near(15.5)
        self.teleport(10.5, 4.4)
        self.tick(5)
        wx, wy = self.pos(worm)
        self.aim(wx, wy, 1)                                                            # left button: shoot at the pointer
        seen = False
        for _ in range(60):
            self.tick(1)
            seen = seen or self.node_with_tag(6) is not None
            if not self.lib.p2d_node_alive(worm):
                break
            wx, wy = self.pos(worm)
            self.aim(wx, wy, 1)
        self.assertTrue(seen)                                                          # (there was a bullet)
        self.assertEqual(self.lib.p2d_node_alive(worm), 0)

    def test_the_lasso_catches_an_anchor_swings_and_lets_go(self):
        lib = self.lib
        self.teleport(58.4, 12.4)
        self.tick(10)
        self.aim(65.5, 13.5, 4)                                                        # right button: throw it at the anchor
        for _ in range(40):
            self.tick(1)
            if self.glob(18) > 0.5:
                break
        self.assertEqual(self.glob(18), 1)                                             # attached
        self.teleport(61.5, 11.0)                                                      # (it steps off the edge: it hangs and swings below the anchor)
        low = 99.0
        for _ in range(45):
            self.tick(1)
            low = min(low, self.pos()[1])
        self.assertLess(low, 9.0)
        self.assertGreater(self.pos()[1], 6.0)                                         # (the rope holds it)
        rope = [n for n in range(lib.p2d_node_slots()) if lib.p2d_node_alive(n) and lib.p2d_node_active(n) and lib.p2d_sprite_info(n, 1) > 3.0]
        self.assertTrue(rope)                                                          # (and the rope is drawn: a long thin sprite)
        self.aim(65.5, 13.5, 0)
        self.tick(3)
        self.assertEqual(self.glob(18), 0)                                             # let go

    def test_a_turret_shoots_arrows_that_hurt(self):
        self.teleport(42.5, 4.4)
        arrow = None
        for _ in range(100):
            self.tick(1)
            arrow = self.node_with_tag(4)
            if arrow is not None:
                break
        self.assertIsNotNone(arrow)
        x0 = self.pos(arrow)[0]
        self.tick(5)
        self.assertLess(self.pos(arrow)[0], x0)                                        # toward the slime
        deaths = self.glob(0)
        self.tick(90)                                                                  # standing still, it is hit
        self.assertGreater(self.glob(0), deaths)

    def test_a_crumbly_platform_dissolves_after_the_slime_has_stood_on_it(self):
        lib = self.lib
        crumbly = self.node_at(33.5, 3.5)
        self.assertIsNotNone(crumbly)
        self.teleport(33.5, 4.4)
        self.tick(50)
        self.assertGreater(self.pos(crumbly)[1], 0)                                    # (not yet)
        self.tick(30)
        self.assertLess(self.pos(crumbly)[1], -50)
        self.tick(120)                                                                 # it falls into the pit and is back at the start
        self.assertAtStart()
        self.assertGreater(self.pos(crumbly)[1], 0)

    def test_a_checkpoint_is_where_it_comes_back_to(self):
        self.teleport(26.5, 4.5)
        self.tick(5)
        self.assertEqual(self.glob(1), 1)
        self.teleport(21.5, 6.0)                                                       # falls into the pit
        self.tick(150)
        x, y = self.pos()
        self.assertAlmostEqual(x, 26.5, 1)
        self.assertEqual(self.glob(0), 1)

    def test_the_bot_plays_the_whole_level_to_the_goal(self):
        lib = self.lib
        goal = self.node_at(80.5, 12.5)
        self.assertIsNotNone(goal)
        self.assertNotEqual(lib.p2d_get_tag(goal), 99)
        lib.p2d_set_global(6, 1.0)                                                     # (the T key does that)
        for frame in range(60 * 60):
            self.tick(1)
            if lib.p2d_get_tag(goal) == 99:
                break
        self.assertEqual(lib.p2d_get_tag(goal), 99, "stopped at %s, %d deaths" % (self.pos(), self.glob(0)))
        self.assertEqual(self.glob(5), 1)
        self.assertGreaterEqual(self.glob(4), 3)                                       # gems on the way
        self.assertGreaterEqual(self.glob(1), 2)                                       # both checkpoints


if __name__ == "__main__":
    unittest.main()

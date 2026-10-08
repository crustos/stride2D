"""Tests of the model and the text formats (no Qt, no engine):  python3 -m unittest stride2d_editor.test_core   (or: python3 stride2d.py --selftest)"""
import json
import os
import tempfile
import unittest
from unittest import mock

from . import fx
from .fxdefs import BY_ID, EFFECTS, PARAM_FLOATS
from .asciiart import (emoji_for_name, export_level, export_levels, export_sprite, export_sprites, import_levels, import_sprites, level_from_text,
                       level_to_text, natural_name, parse_level_text, scan_sprite_text, split_graphemes)
from .demo import make_demo_project
from .model import Level, Palette, Project, ProjectError, Sprite, TileDef, parse_color


def snapshot(project):
    """Everything about a project's sprites that matters to a viewer: each frame's pixels as RGBA, so key letters and index order may differ."""
    return {s.name: (s.width, s.height, s.fps, [s.rgba(project.palette, i) for i in range(len(s.frames))]) for s in project.sprites}


class Graphemes(unittest.TestCase):
    def test_emoji_sequences_are_one_cell(self):
        text = "\U0001f9f1\U0001fa99\U0001f468‍\U0001f469‍\U0001f467\U0001f1fa\U0001f1f8❤️#️⃣A"
        self.assertEqual(len(split_graphemes(text)), 7)

    def test_skin_tone_is_part_of_the_emoji(self):
        self.assertEqual(split_graphemes("\U0001f44d\U0001f3fd\U0001f44d"), ["\U0001f44d\U0001f3fd", "\U0001f44d"])

    def test_natural_names(self):
        self.assertEqual(natural_name("\U0001f9f1"), "brick")
        self.assertEqual(natural_name("\U0001f333"), "deciduous tree")
        self.assertEqual(natural_name("\U0001f1fa\U0001f1f8"), "flag us")
        self.assertEqual(emoji_for_name("Brick"), "\U0001f9f1")
        self.assertIsNone(emoji_for_name("no such emoji name"))


class Palette_(unittest.TestCase):
    def test_transparent_is_index_zero_and_keys_are_unique(self):
        p = Palette()
        self.assertEqual(p.key_of(0), ".")
        self.assertIsNone(p.rgba(0)[3] or None)
        with self.assertRaises(ProjectError):
            p.add("K", "again", (1, 2, 3))
        with self.assertRaises(ProjectError):
            p.add(" ", "bad", (1, 2, 3))
        with self.assertRaises(ProjectError):
            p.add("ab", "bad", (1, 2, 3))
        self.assertEqual(p.add("#", "hash", (1, 2, 3)), len(p) - 1)       # '#' is an ordinary key: ASCII art uses it a lot

    def test_recolouring_an_index_changes_every_frame_that_uses_it(self):
        """The blink: eye pixels use one index, and one colour change turns them all."""
        p = Project("t")
        eye = p.palette.add("E", "eye", (255, 255, 255))
        s = Sprite("face", 4, 2)
        s.frames = [bytearray([eye, 0, 0, eye, 0, 0, 0, 0]), bytearray([0, eye, 0, 0, 0, 0, eye, 0])]
        p.add_sprite(s)
        before = [s.rgba(p.palette, i) for i in range(2)]
        p.palette.set_color(eye, (10, 20, 30))
        after = [s.rgba(p.palette, i) for i in range(2)]
        for b, a in zip(before, after):
            self.assertEqual(len(b), len(a))
            self.assertNotEqual(b, a)
            self.assertEqual(sorted(set(a[i:i + 4] for i in range(0, len(a), 4))), sorted([bytes((10, 20, 30, 255)), bytes((0, 0, 0, 0))]))

    def test_removing_and_moving_entries_keeps_every_pixel_colour(self):
        p = make_demo_project()
        want = snapshot(p)
        p.move_palette_entry(3, 9)
        p.move_palette_entry(9, 2)
        self.assertEqual(snapshot(p), want)
        victim = p.palette.index_of("T")
        used_before = {n for s in p.sprites for f in s.frames for n in f}
        p.remove_palette_entry(victim)
        # the pixels of the removed colour are transparent now, and nothing else changed colour
        grass = p.sprite("grass")
        self.assertIn(0, grass.frames[0])
        self.assertEqual(p.sprite("brick").rgba(p.palette, 0), want["brick"][3][0])
        self.assertTrue(victim in used_before)


class SpriteText(unittest.TestCase):
    def test_export_then_import_is_lossless(self):
        a = make_demo_project()
        text = export_sprites(a)
        b = Project("b")
        b.palette = Palette(with_defaults=False)               # an empty palette: the header alone must bring the colours back
        import_sprites(text, b)
        self.assertEqual(snapshot(a), snapshot(b))
        self.assertEqual([s.name for s in a.sprites], [s.name for s in b.sprites])

    def test_frames_are_blank_line_separated_and_fps_survives(self):
        p = make_demo_project()
        coin = p.sprite("coin")
        self.assertEqual(len(coin.frames), 4)
        text = export_sprite(coin, p.palette)
        self.assertEqual(text.count("\n\n"), 3)
        q = Project("q")
        import_sprites(text, q)
        self.assertEqual(q.sprite("coin").fps, 6.0)
        self.assertEqual(len(q.sprite("coin").frames), 4)

    def test_plain_ascii_art_imports_with_a_mapping(self):
        art = "..##..\n.#@@#.\n..##..\n"
        p = Project("p")
        blocks, unknown = scan_sprite_text(art, p.palette)
        self.assertEqual(sorted(unknown), ["#", "@"])
        sprites, added = import_sprites(art, p, {"#": (200, 0, 0), "@": None})
        s = sprites[0]
        self.assertEqual((s.width, s.height), (6, 3))
        self.assertEqual(s.get(0, 2, 0), p.palette.index_of("#"))
        self.assertEqual(s.get(0, 2, 1), 0)                               # '@' was mapped to transparent
        self.assertEqual(p.palette.entries[p.palette.index_of("#")].rgb, (200, 0, 0))
        self.assertEqual(added, ["#"])
        self.assertIsNone(p.palette.index_of("@"))                        # and a transparent choice adds nothing to the palette

    def test_a_space_is_transparent_and_ragged_rows_are_padded(self):
        p = Project("p")
        (s,), _ = import_sprites("R  R\nRR\nR", p)
        self.assertEqual((s.width, s.height), (4, 3))
        self.assertEqual(s.rows(p.palette, 0), ["R..R", "RR..", "R..."])

    def test_importing_never_recolours_the_existing_palette(self):
        p = Project("p")
        yellow = p.palette.entries[p.palette.index_of("Y")].rgb
        (s,), added = import_sprites("# sprite: x\n# palette: Y=#0000ff\nYY\n", p)
        self.assertEqual(p.palette.entries[p.palette.index_of("Y")].rgb, yellow)     # the project's Y is still its Y
        self.assertEqual(len(added), 1)                                              # the file's blue Y is a new entry under a free key
        self.assertEqual(s.rgba(p.palette, 0)[:4], bytes((0, 0, 255, 255)))

    def test_header_lines_need_their_keyword(self):
        # a row that merely starts with '#' is art, not a header
        p = Project("p")
        (s,), added = import_sprites("# #\n#  \n", p)
        self.assertEqual((s.width, s.height), (3, 2))
        self.assertEqual(added, ["#"])

    def test_errors_say_where(self):
        with self.assertRaises(ProjectError) as e:
            import_sprites("# palette: K=notacolour\nKK\n", Project("p"))
        self.assertIn("line 1", str(e.exception))
        with self.assertRaises(ProjectError):
            import_sprites("\n\n", Project("p"))


class LevelText(unittest.TestCase):
    def test_demo_level_round_trips_through_text(self):
        a = make_demo_project()
        text = export_levels(a)
        b = Project("b")
        b.sprites = [s for s in a.sprites]
        import_levels(text, b)
        la, lb = a.levels[0], b.levels[0]
        self.assertEqual((la.width, la.height, la.cells), (lb.width, lb.height, lb.cells))
        self.assertEqual({k: (t.name, t.solid) for k, t in a.tiles.items()}, {k: (t.name, t.solid) for k, t in b.tiles.items()})

    def test_legend_and_header_are_readable(self):
        a = make_demo_project()
        lines = export_level(a.levels[0], a).splitlines()
        self.assertEqual(lines[0], "# level: first steps")
        self.assertIn("# \U0001f9f1 = brick (solid)", lines)
        self.assertIn("# \U0001fa99 = coin", lines)
        self.assertTrue(all(len(split_graphemes(l)) == 24 for l in lines if not l.startswith("#")))

    def test_tiles_take_their_sprite_by_name(self):
        p = make_demo_project()
        self.assertEqual(p.sprite_for_tile(p.tiles["\U0001f9f1"]).name, "brick")
        # an emoji whose natural name is a sprite's name needs no mapping at all
        q = Project("q")
        import_sprites("# sprite: brick\nRR\nRR\n", q)
        import_levels("\U0001f9f1\U0001f9f1\n", q)
        self.assertEqual(q.tiles["\U0001f9f1"].name, "brick")
        self.assertEqual(q.sprite_for_tile(q.tiles["\U0001f9f1"]).name, "brick")

    def test_ascii_levels_work_even_with_hash_walls(self):
        p = Project("p")
        (lv,), new = import_levels(". . .\n# #  #\n", p)           # a row starting "# " is a row, not a comment
        self.assertEqual(lv.height, 2)
        self.assertEqual(sorted(t.emoji for t in new), ["#"])
        self.assertEqual(natural_name("#"), "number sign")

    def test_ragged_rows_are_padded_with_empty(self):
        p = Project("p")
        (lv,), _ = import_levels("# empty: .\n#..#\n#\n", p)
        self.assertEqual((lv.width, lv.height), (4, 2))
        self.assertEqual(lv.get(3, 1), "")

    def test_two_levels_in_one_file(self):
        p = Project("p")
        made, _ = import_levels("# level: a\n\U0001f9f1\n# level: b\n\U0001fa99\U0001fa99\n", p)
        self.assertEqual([l.name for l in made], ["a", "b"])
        self.assertEqual(made[1].width, 2)

    def test_text_pane_edit(self):
        p = make_demo_project()
        lv = p.levels[0]
        text = level_to_text(lv, p)
        self.assertEqual(len(text.splitlines()), lv.height)
        new_tiles = level_from_text(lv, text.replace("\U0001fa99", "\U0001f333", 1), p)
        self.assertEqual([t.name for t in new_tiles], ["deciduous tree"])
        self.assertEqual(level_to_text(lv, p).count("\U0001f333"), 1)

    def test_resize_and_fill(self):
        lv = Level("l", 4, 3)
        lv.flood_fill(0, 0, "X")
        self.assertEqual(lv.cells.count("X"), 12)
        lv.set(1, 1, "Y")
        lv.resize(2, 2)
        self.assertEqual(lv.cells, ["X", "X", "X", "Y"])

    def test_no_level_is_an_error(self):
        with self.assertRaises(ProjectError):
            parse_level_text("# level: nothing\n")


class JsonProject(unittest.TestCase):
    def test_round_trip_through_a_file(self):
        a = make_demo_project()
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "demo.json")
            a.save(path)
            b = Project.load(path)
            self.assertEqual(snapshot(a), snapshot(b))
            self.assertEqual(a.levels[0].cells, b.levels[0].cells)
            with open(path, encoding="utf-8") as f:
                self.assertEqual(json.load(f), b.to_json())
            self.assertFalse(b.dirty)

    def test_the_file_reads_like_the_art(self):
        data = make_demo_project().to_json()
        self.assertEqual(data["sprites"][0]["frames"][0][0], "SSSSSSSS")
        self.assertEqual(data["levels"][0]["rows"][10], "\U0001f7e9" * 24)

    def test_bad_files_say_where(self):
        good = make_demo_project().to_json()
        bad = json.loads(json.dumps(good))
        bad["sprites"][1]["frames"][0][2] = "ZZZZZZZZ"
        with self.assertRaises(ProjectError) as e:
            Project.from_json(bad)
        self.assertIn("sprites[1].frames[0]", str(e.exception))
        self.assertIn("'Z'", str(e.exception))
        bad = json.loads(json.dumps(good))
        bad["levels"][0]["rows"][0] = "\U0001f4a5" * 24
        with self.assertRaises(ProjectError) as e:
            Project.from_json(bad)
        self.assertIn("levels[0]", str(e.exception))
        with self.assertRaises(ProjectError):
            Project.from_json({"format": "something else"})
        bad = json.loads(json.dumps(good))
        bad["version"] = 99
        with self.assertRaises(ProjectError):
            Project.from_json(bad)

    def test_parse_color(self):
        self.assertEqual(parse_color("#fff"), (255, 255, 255))
        self.assertEqual(parse_color("0a0b0c"), (10, 11, 12))
        with self.assertRaises(ProjectError):
            parse_color("red")

    def test_sprite_edit_operations(self):
        s = Sprite("s", 3, 2)
        s.set(0, 1, 1, 5)
        n = s.add_frame(0, copy=True)
        self.assertEqual(s.get(n, 1, 1), 5)
        s.set(n, 0, 0, 7)
        s.resize(2, 3)
        self.assertEqual((s.width, s.height, s.get(n, 0, 0), s.get(n, 1, 1)), (2, 3, 7, 5))
        s.flood_fill(0, 0, 0, 9)
        self.assertEqual(s.get(0, 0, 0), 9)
        self.assertEqual(s.move_frame(0, 1), 1)
        s.delete_frame(0)
        self.assertEqual(len(s.frames), 1)
        s.delete_frame(0)
        self.assertEqual(len(s.frames), 1)                    # the last frame stays


class SlimeProject(unittest.TestCase):
    def test_the_sample_level_becomes_a_project_that_round_trips(self):
        from .slime_demo import make_slime_project
        from .asciiart import export_level, import_levels
        p = make_slime_project()
        lv = p.levels[0]
        dirt, stone, worm = "\U0001f7eb", "\U0001f9f1", "\U0001fab1"
        self.assertEqual((lv.width, lv.height), (64, 20))
        self.assertEqual((lv.cells.count(worm), lv.cells.count("\U0001f7e2")), (1, 1))     # one worm, one slime
        self.assertGreater(lv.cells.count(dirt), 150)                       # the platforms and the tower are ground...
        self.assertGreater(lv.cells.count(stone), 150)                      # ...and the floor, ceiling and outer walls are bedrock
        self.assertTrue(p.tiles[dirt].diggable and p.tiles[dirt].solid and not p.tiles[stone].diggable)
        p.tiles["\U0001f4e6"] = TileDef("\U0001f4e6", "crate", "", False, True, False)   # a movable body, to see that trait travel too
        p2 = Project.from_json(p.to_json())
        self.assertEqual(p2.levels[0].cells, lv.cells)
        self.assertTrue(p2.tiles[dirt].diggable and p2.tiles["\U0001f4e6"].dynamic)
        lv.cells[5] = "\U0001f4e6"
        q = Project("again")                                                # the emoji text keeps the traits too
        import_levels(export_level(lv, p), q)
        self.assertTrue(q.tiles[dirt].diggable and q.tiles[dirt].solid and q.tiles["\U0001f4e6"].dynamic)
        self.assertEqual(q.levels[0].cells, lv.cells)


class Effects(unittest.TestCase):
    """The effect registry as Python sees it (fxdefs.py is generated from src/native/gfx2d/fx/*.fx) and how values are packed for gfx_effect."""

    def test_registry_is_consistent(self):
        self.assertTrue(EFFECTS)
        self.assertEqual(len({e["id"] for e in EFFECTS.values()}), len(EFFECTS))
        for name, e in EFFECTS.items():
            self.assertEqual(BY_ID[e["id"]], name)
            for p in e["params"]:
                self.assertLessEqual(p["offset"] + p["size"], PARAM_FLOATS)
                self.assertEqual(len(p["default"]), p["size"])
                if p["type"] == "color":
                    self.assertEqual(p["offset"] % 4, 0, "a color is read as one vec4 on the GPU")
                else:
                    self.assertTrue(p["min"] <= p["default"][0] <= p["max"])

    def test_defaults_when_nothing_is_given(self):
        eid, floats = fx.pack("tint")
        self.assertEqual(eid, EFFECTS["tint"]["id"])
        self.assertEqual(len(floats), PARAM_FLOATS)
        self.assertEqual(floats[:5], [1.0, 0.5, 0.1, 1.0, 0.5])      # the colour, then the amount: what tint.fx says
        self.assertEqual(fx.defaults("bright_contrast"), {"brightness": 0.0, "contrast": 0.0})

    def test_values_land_where_the_registry_says(self):
        _, floats = fx.pack("bright_contrast", {"contrast": 0.25})
        self.assertEqual(floats[:2], [0.0, 0.25])
        _, floats = fx.pack("tint", {"color": (0.2, 0.4, 0.6), "amount": 1.0})
        self.assertEqual(floats[:5], [0.2, 0.4, 0.6, 1.0, 1.0])        # three numbers: alpha 1

    def test_values_are_brought_into_range(self):
        _, floats = fx.pack("bright_contrast", {"brightness": 9, "contrast": -9})
        self.assertEqual(floats[:2], [1.0, -1.0])
        _, floats = fx.pack("tint", {"color": (2, -1, 0.5, 7)})
        self.assertEqual(floats[:4], [1.0, 0.0, 0.5, 1.0])

    def test_refusals(self):
        with self.assertRaises(KeyError):
            fx.pack("no_such_effect")
        with self.assertRaises(KeyError):
            fx.pack("tint", {"hue": 1})
        with self.assertRaises(ValueError):
            fx.pack("tint", {"amount": float("nan")})
        with self.assertRaises(ValueError):
            fx.pack("tint", {"color": (1, 2)})

    def test_int_bool_and_enum_parameters(self):
        demo = {"id": 200, "title": "Demo", "group": "", "nparams": 3, "params": [
            {"name": "steps", "type": "int", "label": "Steps", "offset": 0, "size": 1, "min": 1.0, "max": 8.0, "default": [4.0]},
            {"name": "flip", "type": "bool", "label": "Flip", "offset": 1, "size": 1, "min": 0.0, "max": 1.0, "default": [0.0]},
            {"name": "mode", "type": "enum", "label": "Mode", "offset": 2, "size": 1, "min": 0.0, "max": 2.0, "default": [0.0], "options": ["Add", "Mul", "Screen"]}]}
        with mock.patch.dict(EFFECTS, {"demo": demo}):
            _, floats = fx.pack("demo", {"steps": 2.6, "flip": True, "mode": "Screen"})
            self.assertEqual(floats[:3], [3.0, 1.0, 2.0])               # an int is rounded, a bool is 0 or 1, an enum may be named by its label
            _, floats = fx.pack("demo", {"steps": 99, "mode": 1})
            self.assertEqual(floats[:3], [8.0, 0.0, 1.0])
            with self.assertRaises(ValueError):
                fx.pack("demo", {"mode": "Divide"})


if __name__ == "__main__":
    unittest.main()


class LevelEffects(unittest.TestCase):
    def project(self):
        from .model import Level, Project
        p = Project("fx")
        lv = p.add_level(Level("a", 3, 2))
        lv.effects = [{"effect": "blend", "values": {"mode": 12, "color": [0.1, 0.2, 0.3, 0.4], "opacity": 0.5}, "enabled": False},
                      {"effect": "levels", "values": {"gamma": 2.0}, "enabled": True}]
        p.add_level(Level("b", 2, 2))
        return p

    def test_effects_survive_the_json_round_trip_and_a_level_without_any_writes_none(self):
        from .model import Project
        p = self.project()
        data = p.to_json()
        self.assertNotIn("effects", data["levels"][1])
        back = Project.from_json(json.loads(json.dumps(data)))
        self.assertEqual(back.levels[0].effects, p.levels[0].effects)
        self.assertEqual(back.levels[1].effects, [])

    def test_a_project_with_a_bad_effect_is_refused_with_the_place(self):
        from .model import Project, ProjectError
        good = self.project().to_json()
        for what, edit in (("an unknown effect", lambda e: e.update(effect="nope")),
                           ("an unknown parameter", lambda e: e.update(values={"nope": 1})),
                           ("a value that is not a number", lambda e: e.update(values={"gamma": "x"})),
                           ("effects that are not a list", None)):
            data = json.loads(json.dumps(good))
            if edit:
                edit(data["levels"][0]["effects"][1])
            else:
                data["levels"][0]["effects"] = {}
            with self.assertRaises(ProjectError, msg=what) as cm:
                Project.from_json(data)
            self.assertIn("levels[0]", str(cm.exception), what)


class ViewportEffects(unittest.TestCase):
    """The viewport hands the level's enabled effects to the engine in order (the engine is a recorder here, so no library is needed)."""

    def test_enabled_effects_are_queued_in_order_and_bad_entries_skipped(self):
        from .engine import Viewport
        from .model import Level, Project
        calls = []

        class Recorder:
            def effect(self, name, values=None):
                from .fx import pack
                pack(name, values)
                calls.append((name, values))

        lv = Level("l", 2, 2)
        lv.effects = [{"effect": "tint", "values": {"amount": 0.3}, "enabled": True},
                      {"effect": "blend", "values": {}, "enabled": False},
                      {"effect": "gone", "values": {}, "enabled": True},
                      {"effect": "levels", "values": {"gamma": 2.0}}]
        vp = Viewport(Recorder(), Project())
        vp._apply_effects(lv)
        vp._apply_effects(None)
        self.assertEqual(calls, [("tint", {"amount": 0.3}), ("levels", {"gamma": 2.0})])


class LevelLights(unittest.TestCase):
    def level(self):
        from .model import Level
        lv = Level("l", 10, 6)
        from . import lights as L
        lv.lights = [L.new_light("point", 2, 1), L.new_light("spot", 8, 4)]
        lv.lights[1]["enabled"] = False
        return lv

    def test_more_lights_than_the_effect_takes_are_chosen_by_the_camera(self):
        from .model import Level
        from . import lights as L
        lv = Level("cave", 100, 20)
        lv.lights = [L.new_light("point", x + 0.5, 10.5) for x in range(0, 100, 5)]      # 20 lights, 5 cells apart, radius 4
        near = L.effect_values(lv, 50.0, 9.5, 4.0, 2.0)                                  # a view 16 cells wide at x 50
        xs = sorted(round(near["l%dx" % i] * 16 + 50 - 8, 1) for i in range(L.MAX_SHADER_LIGHTS) if near.get("l%dk" % i, 0) > 0)
        self.assertEqual(xs, [40.5, 45.5, 50.5, 55.5, 60.5])                             # only the lights that reach the picture are given, the rest are off
        far = L.effect_values(lv, 20.0, 9.5, 4.0, 2.0)
        self.assertEqual(sorted(round(far["l%dx" % i] * 16 + 20 - 8, 1) for i in range(L.MAX_SHADER_LIGHTS) if far.get("l%dk" % i, 0) > 0), [10.5, 15.5, 20.5, 25.5, 30.5])
        lv.lights = [L.new_light("point", 50.5, 10.5) for _ in range(12)]                # all in view: eight are used
        self.assertEqual(sum(1 for i in range(8) if L.effect_values(lv, 50.0, 9.5, 4.0, 2.0).get("l%dk" % i, 0) > 0), 8)
        self.assertEqual(L.MAX_LIGHTS, 64)

    def test_lights_and_lighting_round_trip_and_a_plain_level_writes_neither(self):
        from .model import Level, Project
        p = Project("p")
        lv = p.add_level(self.level())
        lv.lighting["glow"] = 0.4
        p.add_level(Level("plain", 2, 2))
        data = json.loads(json.dumps(p.to_json()))
        self.assertNotIn("lights", data["levels"][1])
        self.assertNotIn("lighting", data["levels"][1])
        back = Project.from_json(data)
        self.assertEqual(back.levels[0].lights, lv.lights)
        self.assertEqual(back.levels[0].lighting, lv.lighting)
        self.assertEqual(back.levels[1].lights, [])

    def test_bad_lights_are_refused_with_the_place_and_numbers_are_brought_into_range(self):
        from .model import Project, ProjectError
        p = Project("p")
        p.add_level(self.level())
        good = p.to_json()
        for what, edit in (("an unknown kind", lambda d: d["lights"][0].update(kind="laser")), ("a NaN", lambda d: d["lights"][0].update(x=float("nan"))),
                           ("a color of two numbers", lambda d: d["lights"][0].update(color=[1, 1])), ("lights not a list", lambda d: d.update(lights={}))):
            data = json.loads(json.dumps(good, allow_nan=True))
            edit(data["levels"][0])
            with self.assertRaises(ProjectError, msg=what) as cm:
                Project.from_json(data)
            self.assertIn("levels[0]", str(cm.exception), what)
        data = json.loads(json.dumps(good))
        data["levels"][0]["lights"][0]["intensity"] = 99
        self.assertEqual(Project.from_json(data).levels[0].lights[0]["intensity"], 4.0)

    def test_the_effect_values_follow_the_camera(self):
        from . import lights as L
        from .fx import pack
        lv = self.level()
        lv.lights[1]["enabled"] = True
        # a camera on the level's middle (5, 3) that sees 3 cells up and down and is 5/3 as wide as high
        v = L.effect_values(lv, 5.0, 3.0, 3.0, 5.0 / 3.0)
        self.assertAlmostEqual(v["l0x"], (2 - 5) / (2 * 3 * 5 / 3) + 0.5)       # 3 cells left of the middle: 0.2
        self.assertAlmostEqual(v["l0y"], 0.5 - ((6 - 1) - 3) / 6.0)              # the level's row 1 is 2 cells above the middle: y 1/6 from the top
        self.assertAlmostEqual(v["l0r"], 4 / 6.0)
        self.assertEqual((v["l0t"], v["l1t"]), (0, 1))
        self.assertEqual(pack("scene_lights", v)[0], 16)
        panned = L.effect_values(lv, 6.0, 3.0, 3.0, 5.0 / 3.0)                   # the camera moved right: the light moves left on the screen
        self.assertLess(panned["l0x"], v["l0x"])
        lv.lights[1]["enabled"] = False
        self.assertNotIn("l1x", L.effect_values(lv, 5.0, 3.0, 3.0, 5.0 / 3.0))
        lv.lights[0]["enabled"] = False
        self.assertIsNone(L.effect_values(lv, 5.0, 3.0, 3.0, 5.0 / 3.0))
        lv.lights[0]["enabled"] = True
        lv.lighting["enabled"] = False
        self.assertIsNone(L.effect_values(lv, 5.0, 3.0, 3.0, 5.0 / 3.0))

    def test_the_viewport_hands_the_lights_to_the_engine_before_the_effects(self):
        from .engine import Viewport
        from .model import Project
        calls = []

        class Recorder:
            def effect(self, name, values=None):
                from .fx import pack
                pack(name, values)
                calls.append(name)

        lv = self.level()
        lv.effects = [{"effect": "tint", "values": {}, "enabled": True}]
        vp = Viewport(Recorder(), Project())
        vp._apply_lights(lv)
        vp._apply_effects(lv)
        self.assertEqual(calls, ["scene_lights", "tint"])



class CaveDemo(unittest.TestCase):
    """samples/SlimeCave: the project, and the stand-in bot that plays it (no renderer, no engine)."""

    def test_project_is_valid_lit_and_dressed(self):
        from .cave_demo import make_cave_project
        from .fx import pack
        from .model import Project
        from . import lights as L
        p = make_cave_project()
        lv = p.levels[0]
        self.assertEqual((lv.width, lv.height), (100, 18))
        self.assertGreater(len(lv.lights), L.MAX_SHADER_LIGHTS)                         # more than one picture takes: the camera picks
        self.assertLessEqual(len(lv.lights), L.MAX_LIGHTS)
        for fx in lv.effects:
            pack(fx["effect"], fx["values"])                                            # every effect and value is one the registry accepts
        back = Project.from_json(json.loads(json.dumps(p.to_json())))
        self.assertEqual(back.levels[0].cells, lv.cells)
        self.assertEqual(back.levels[0].lights, lv.lights)
        self.assertEqual(back.levels[0].effects, lv.effects)
        for e in {c for c in lv.cells if c}:
            self.assertIn(e, p.tiles)                                                   # every emoji in the level is a tile, and every tile has its sprite
        for t in p.tiles.values():
            self.assertTrue(any(s.name == t.sprite for s in p.sprites), t.name)

    def test_the_bot_digs_through_the_cave_in_shoots_and_reaches_the_flag(self):
        from .cave_demo import CaveSim, cave_frame_effects, cave_frame_lights, make_cave_project
        from .fx import pack
        from . import lights as L
        p = make_cave_project()
        lv = p.levels[0]
        before = list(lv.cells)
        sim = CaveSim(p, lv)
        seen = 0
        for i in range(60 * 30):
            sim.step(1 / 60.0)
            if i % 30 == 0:
                vals = L.effect_values(cave_frame_lights(sim), sim.cx, sim.cy, sim.half, 16 / 9.0)
                self.assertIsNotNone(vals)
                seen = max(seen, sum(1 for k in range(8) if vals.get("l%dk" % k, 0) > 0))
                for fx in cave_frame_effects(sim):
                    pack(fx["effect"], fx["values"])
            if sim.done and sim.done_t > 0.5:
                break
        self.assertTrue(sim.done, sim.log)
        self.assertLess(sim.t, 25.0)
        self.assertEqual(lv.cells, before)                                              # playing never changes the project
        self.assertTrue(any(l.startswith("crater") for l in sim.log))                   # the dirt was dug...
        self.assertTrue(any("burst" in l for l in sim.log))                             # ...and something shot
        self.assertGreaterEqual(sim.gems_taken, 8)
        self.assertEqual(seen, 8)                                                       # the lights of a frame fill the effect's eight places
        again = CaveSim(p, lv)                                                          # and it is deterministic
        for _ in range(int(sim.t * 60)):
            again.step(1 / 60.0)
        self.assertEqual((again.x, again.y, again.gems_taken), (sim.x, sim.y, sim.gems_taken))

#!/usr/bin/env python3
"""stride2d.py -- the Stride2D 2D editor (PyQt5). No .NET: the engine is libstride2d.so (the C# runtime translated to C), called through ctypes.

    python3 stride2d.py [project.json]        open the editor (a demo project if none is given)
    python3 stride2d.py --demo cave           open samples/SlimeCave: a lit cave (Effects and Lights windows show how it is made); tools/cave_gif.py plays it into a GIF
    python3 stride2d.py --demo slime          open samples/SlimeJumpDestruct as a project and play it in the viewport (the dirt wall is dug, crates burst)
    python3 stride2d.py --demo slime-rust     open SlimeJump with its game logic in Rust scripts (samples/SlimeJumpRust): press F5 to build them, then play (arrows or A/D, space, mouse: blaster and lasso, T: the bot)
    python3 stride2d.py --viewport [...]      also open the engine's window on the first level
    python3 stride2d.py --export-ascii DIR project.json     no GUI: write the project's sprites and levels as ASCII art / emoji text into DIR
    python3 stride2d.py --import-ascii OUT.json [--sprites A.txt ...] [--levels B.txt ...]    no GUI: build a project from ASCII art and emoji levels
    python3 stride2d.py --import-unity OUT.json --unity DIR [DIR|FILE.png ...] [--cell N] [--no-scenes]    no GUI: import the 2D sprites (PNGs, sprite sheets) and scenes (as levels) of a Unity project into OUT.json
    python3 stride2d.py --selftest            run the tests (the model and text formats, then the GUI windows if PyQt5 is installed)
    python3 stride2d.py --screenshots DIR     draw every window to a PNG in DIR (works without a display) and exit
    python3 stride2d.py --quit-after SECONDS  close the editor by itself after a while, as if the user quit (for smoke tests)

The editor is several floating windows (project / palette / sprite editor / level editor); the viewport is the engine's own window. Build the engine once:

    python3 tools/engine_so.py            -> /tmp/libstride2d.so   (set STRIDE2D_LIB to use another path)

Scripts: the Scripts window is a small code editor for the project's scripts (C#, C++, Rust or RPython, picked next to New script; saved in the project file). Mark a class
[Script, MaxInstances(N)] with `public Component Self;` and callbacks (Update, OnCollisionBegin2D ...), tick it for a sprite (it runs on every tile showing that sprite) or for the
game (once per play), and press F5: the scripts are translated to C with the engine (needs the .NET SDK, about a minute), a new engine library is linked, the viewport's window
closes and opens again on it. Errors come back with their line. Scripts read keys and the mouse with Input2D (src/engine/Input2D.cs). Only the C# subset builds
(tools/ccsharp/README.md); the C++, Rust and RPython scripts are lowered to C by Crust's front ends and linked in too (tools/script_native.py; EDITOR.md, Scripts).

Without it everything but the viewport works. Sprites are indexed-palette pixel art (a letter per colour); levels are grids of emoji tiles, which an
exported level shows as text. See stride2d_editor/asciiart.py for both formats.
"""
import argparse
import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)


def load_project(path, demo=None):
    from stride2d_editor.model import Project
    from stride2d_editor.demo import make_demo_project
    if path:
        return Project.load(path)
    if demo == "slime":
        from stride2d_editor.slime_demo import make_slime_project
        return make_slime_project()
    if demo == "cave":
        from stride2d_editor.cave_demo import make_cave_project
        return make_cave_project()
    if demo == "slime-rust":
        from stride2d_editor.slime_rust import make_slime_rust_project
        return make_slime_rust_project()
    return make_demo_project()


def cmd_export_ascii(out_dir, path):
    from stride2d_editor.fileio import export_folder
    p = load_project(path)
    n = export_folder(p, out_dir)
    print("wrote %d file(s) to %s (%d sprites, %d levels)" % (n, out_dir, len(p.sprites), len(p.levels)))
    return 0


def cmd_import_ascii(out_json, sprites, levels):
    from stride2d_editor import asciiart, fileio
    from stride2d_editor.model import Project
    p = Project(fileio.stem(out_json))
    for path in sprites:
        text = fileio.name_first_sprite(fileio.read_text(path), fileio.stem(path))
        made, added = asciiart.import_sprites(text, p)
        print("sprites %s from %s%s" % (", ".join(s.name for s in made), path, "  (new palette keys: %s)" % " ".join(added) if added else ""))
    for path in levels:
        made, new = asciiart.import_levels(fileio.read_text(path), p, fileio.stem(path))
        print("levels %s from %s%s" % (", ".join(l.name for l in made), path, "  (new tiles: %s)" % " ".join(t.emoji for t in new) if new else ""))
    p.save(out_json)
    print("wrote", out_json)
    return 0


def cmd_import_unity(out_json, roots, scenes=True, cell=None):
    from stride2d_editor import fileio
    from stride2d_editor.model import Project
    from stride2d_editor.unity_scene import import_unity_project
    if not roots:
        print("--import-unity needs --unity DIR (a Unity project folder, any folder of PNGs, or a PNG)", file=sys.stderr)
        return 2
    p = Project.load(out_json) if os.path.exists(out_json) else Project(fileio.stem(out_json))      # an existing project is added to
    for root in roots:
        report = import_unity_project(p, root, scenes=scenes, cell=cell)
        print("%s: %s" % (root, report.summary()))
        for note in report.notes:
            print("  note:", note)
    p.save(out_json)
    print("wrote", out_json)
    return 0


def cmd_selftest():
    import unittest
    names = ["stride2d_editor.test_core"]
    try:
        import PyQt5  # noqa: F401
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        names.append("stride2d_editor.test_gui")
        names.append("stride2d_editor.test_engine")
    except ImportError:
        print("(PyQt5 is not installed: only the model and text-format tests run)")
    suite = unittest.defaultTestLoader.loadTestsFromNames(names)
    return 0 if unittest.TextTestRunner(verbosity=1).run(suite).wasSuccessful() else 1


def make_app(argv):
    from PyQt5 import QtWidgets
    from stride2d_editor import gui
    app = QtWidgets.QApplication(argv)
    return app, gui


def cmd_screenshots(out_dir, project_path, demo=None):
    if not os.environ.get("DISPLAY") and not os.environ.get("WAYLAND_DISPLAY"):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app, gui = make_app(sys.argv[:1])
    studio = gui.Studio(load_project(project_path, demo))
    main, windows = gui.create_windows(studio)
    os.makedirs(out_dir, exist_ok=True)
    shots = [("project", main)] + [(k, w) for k, w in windows.items()]
    for _, w in shots:
        w.show()
    studio.select_tile(next(iter(studio.project.tiles)))
    for _ in range(5):
        app.processEvents()
    for name, w in shots:
        path = os.path.join(out_dir, "%s.png" % name)
        w.grab().save(path)
        print("wrote", path)
    # the level editor again, as emoji
    windows["levels"].canvas.view = "emoji"
    windows["levels"].canvas.update()
    app.processEvents()
    path = os.path.join(out_dir, "levels_emoji.png")
    windows["levels"].grab().save(path)
    print("wrote", path)
    return 0


def cmd_gui(project_path, open_viewport, quit_after=None, demo=None):
    app, gui = make_app(sys.argv[:1])
    studio = gui.Studio(load_project(project_path, demo))
    main, windows = gui.create_windows(studio)
    gui.tile_windows(main, windows)
    main.show()
    for w in windows.values():
        w.show()
    from PyQt5 import QtCore
    if demo == "slime":                          # show the slime's sprite (and its blinking eyes) and the dirt tile in the editors
        studio.select_sprite(next(sp for sp in studio.project.sprites if sp.name == "slime"))
        studio.select_tile(next(k for k, t in studio.project.tiles.items() if t.name == "dirt"))
    if demo == "slime":                          # SlimeJumpDestruct: the viewport plays it with a stand-in for the sample's bot
        from stride2d_editor.slime_demo import SlimeDriver
        main.viewport.driver_factory = SlimeDriver
        main.viewport.autoplay = True
    if demo == "cave":                           # SlimeCave: the level with its lights and effects, to look at and change (the animation is tools/cave_gif.py)
        studio.select_level(studio.project.levels[0])
        studio.select_sprite(next(sp for sp in studio.project.sprites if sp.name == "slime"))
    if open_viewport or demo == "slime":
        QtCore.QTimer.singleShot(200, main.viewport.open)
    if quit_after:
        QtCore.QTimer.singleShot(int(quit_after * 1000), main.close)
    return app.exec_()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("project", nargs="?", help="a project .json (default: the demo project)")
    ap.add_argument("--demo", choices=["coins", "slime", "cave", "slime-rust"], help="open a built-in project: 'slime' is samples/SlimeJumpDestruct, played in the viewport; 'slime-rust' is SlimeJump in Rust (press F5 to build it); 'cave' is samples/SlimeCave, a dark cave with lights and effects")
    ap.add_argument("--viewport", action="store_true", help="also open the engine's window")
    ap.add_argument("--export-ascii", metavar="DIR", help="no GUI: write sprites/ and levels/ text files of the project into DIR")
    ap.add_argument("--import-ascii", metavar="OUT.json", help="no GUI: build a project from --sprites and --levels text files")
    ap.add_argument("--import-unity", metavar="OUT.json", help="no GUI: import the 2D sprites and scenes of the --unity folders (or PNG files) into OUT.json (added to it if it exists)")
    ap.add_argument("--cell", type=float, metavar="UNITS", help="with --import-unity: the grid cell for scenes, in world units (default: the Grid's cell size, else the size of the most common sprite)")
    ap.add_argument("--no-scenes", action="store_true", help="with --import-unity: import the sprites only, no levels from scenes")
    ap.add_argument("--unity", nargs="*", default=[], metavar="DIR", help="a Unity project folder, any folder of PNGs, or a PNG file")
    ap.add_argument("--sprites", nargs="*", default=[], metavar="FILE.txt")
    ap.add_argument("--levels", nargs="*", default=[], metavar="FILE.txt")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--screenshots", metavar="DIR")
    ap.add_argument("--quit-after", type=float, metavar="SECONDS", help=argparse.SUPPRESS)
    a = ap.parse_args()
    try:
        if a.selftest:
            return cmd_selftest()
        if a.export_ascii:
            return cmd_export_ascii(a.export_ascii, a.project)
        if a.import_ascii:
            return cmd_import_ascii(a.import_ascii, a.sprites, a.levels)
        if a.import_unity:
            return cmd_import_unity(a.import_unity, a.unity, not a.no_scenes, a.cell)
        if a.screenshots:
            return cmd_screenshots(a.screenshots, a.project, a.demo)
        return cmd_gui(a.project, a.viewport, a.quit_after, a.demo)
    except Exception as e:                        # a bad file is a message, not a traceback
        from stride2d_editor.model import ProjectError
        if isinstance(e, (ProjectError, OSError)):
            print("stride2d.py: %s" % e, file=sys.stderr)
            return 1
        raise


if __name__ == "__main__":
    sys.exit(main())

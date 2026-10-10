# stride2d.py — the dotnet-free 2D editor

PyQt5 editor (floating windows) over the engine, which is the C# runtime translated to C and loaded with ctypes.

    python3 build.py so            # builds /tmp/libstride2d.so (+ libstride2d.h); STRIDE2D_LIB overrides the path
    python3 stride2d.py [project.json] [--viewport]
    python3 stride2d.py --demo slime  # samples/SlimeJumpDestruct, played in the viewport
    python3 stride2d.py --export-ascii DIR project.json
    python3 stride2d.py --import-ascii OUT.json --sprites a.txt … --levels b.txt …
    python3 stride2d.py --selftest    # model, GUI (offscreen), engine tests; run under xvfb-run for the viewport tests

Windows: Project (File menu), Palette, Sprite editor, Level editor, Effects, and the engine's own window (built with `python3 build.py so`, or point `STRIDE2D_LIB` at a prebuilt libstride2d.so) (P play, R reset, Home fit, wheel zoom, right-drag pan).

## Effects
The Effects window (Window menu) holds a level's picture effects as a stack, first to last: Add effect (grouped menu), Up / Down, Duplicate, Remove, Reset, and a check box to switch one off.
The controls of the selected effect are built from the effect registry (src/native/gfx2d/fx/*.fx, generated into fxdefs.py), so a new .fx file shows up here with no GUI code:
a slider and number box per float, a color button with alpha, a combo box per enum. The viewport applies the stack live, in play mode too. Each change is an undo step
(a slider drag is one). In the project JSON a level has `"effects": [{"effect": "tint", "values": {"amount": 0.5}, "enabled": true}]`; a project naming an unknown effect or
parameter is refused with the place.

## Lights
The Lights window (and the Lights tool of the level editor) put up to 64 point or spot lights in a level, over an ambient color (one picture is lit by 8 at a time: the ones nearest the camera whose light reaches it): `lights` and `lighting` in a level's JSON.
A light has a place in cells (x right, y down from the top edge), a radius in cells, an intensity, a color, and for a spot a direction, cone and edge softness. In the level editor's Lights tool,
click an empty place to add a light, drag one to move it, right-click one to remove it. The viewport lights its picture with them live (before the level's effects), and they stay
where they were put when the camera pans or zooms. Moving a light, or a slider, is one undo step.

## Sand
The Sand window (Window menu, or S in the viewport) switches on falling sand and flowing water in the viewport, simulated on the CPU by `src/terrain/SandSim.cs` (the same simulation the games use), driven by the engine
(`SandInit`, `SandBrush`, `SandStep`, `SandDraw` in src/engine/Engine.cs) and drawn as one textured quad over the level. The left mouse button paints sand, water, stone or erases (keys 1 2 3, 0; `[` `]` change the brush;
Space pauses, C clears). The level's solid tiles are stone to it. Settings: brush radius, steps a frame, cells to a tile (a big level gets fewer, at most 400 x 400 cells in all). It is a picture: balls and bodies do not touch it.
It is not saved in the project. The same painting with the same seed gives the same grain every time (`p2d_sand_hash`).

## Scripts (code editor)
The Scripts window (Window menu, or the Scripts button) is a code editor for the project's C#: a file list, an editor with line numbers and colours, and a problems list.
A script is a class marked `[Script, MaxInstances(N)]` with `public Component Self;` and Unity-style callbacks (Update, OnCollisionBegin2D, ...); *New script* writes a template.
Tick the class under *Runs on the sprite* (it runs on every tile showing that sprite) or *Runs in the game* (once, on a node of its own, whenever a level plays). Scripts read keys and
the mouse with `Input2D` (`Input2D.Key(Input2D.Left)`, `Input2D.Key('A')`, `Input2D.MouseX`, `Input2D.MouseDown(0)`; src/engine/Input2D.cs).

**Build (F5)** writes the files to a work folder, runs `tools/engine_so.py --scripts DIR` (the engine and the scripts translated to C together, a new libstride2d linked), and swaps it in:
the viewport's window closes and opens again on the new library, at the same camera, playing again if it was. It needs the .NET SDK for the translator and takes about a minute. Only the C#
subset builds (tools/ccsharp/README.md); a line outside it comes back in the problems list with its file and line (double-click to go there), and the old engine stays in use.
Scripts are saved in the project JSON (`"scripts": [{"name", "text"}]`, `"game_scripts": [...]`, and `"scripts": [...]` on a sprite).

## Project JSON
`{"format":"stride2d-project","version":1, palette, sprites, tiles, levels}`. Sprite frames are rows of palette key letters; `.` is index 0 (transparent).
Recolouring an index recolours every pixel that uses it, so scripts animate by changing one palette entry.

## Sprite ASCII
    # sprite: coin
    # fps: 6
    # palette: Y=#ffd23c O=#e08a1e
    .YY.
    YOOY
    (blank line between frames)
Unknown letters on import are mapped to colours in a dialog (or guessed).

## Level emoji
    # level: first steps
    # empty: ⬛
    # 🧱 = brick (solid) -> brick
    ⬛⬛🪙⬛
    🧱🧱🧱🧱
Emoji names come from Unicode (🧱 → "brick") and link to the sprite with the same name; view as emoji or sprites.

Tiles can be `solid` (static collider), `dynamic` (a movable body, like a crate) and `diggable` (a blast removes it, like dirt); the emoji legend writes them as `# 📦 = crate (dynamic) -> crate`. In the viewport's play mode a click drops a ball and B blasts at the pointer.

## Unity import (2D)
File > Import > *Unity project: sprites and scenes as levels...* (or `python3 stride2d.py --import-unity OUT.json --unity DIR`; `--no-scenes` for sprites only, `--cell N` to choose the grid) reads a Unity project folder
(its text-serialized `.unity` scenes, `.prefab` files and PNG textures with their `.meta` files) and adds sprites and levels to the project. *Unity 2D sprites...* and *Unity PNG textures...* import the pictures alone.

- **Sprites**: every PNG that is a sprite in Unity. A Multiple-mode sheet is cut into its slices (a `walk_0`, `walk_1` series of one size becomes the frames of one sprite `walk`; slices Unity named after their own texture, such as a tileset's `tiles_0`, `tiles_1`, stay separate).
  Colours join the palette (the nearest are merged past 256); a texture over 256 px is scaled down.
- **Levels**: one per scene. Each enabled sprite is placed by its world position (parents and prefab instances applied), on a grid of the Grid's cell size (else the most common sprite size), the highest sorting order winning a shared cell.
  Tilemap tiles are placed the same way. A tile is `solid` with a 2D collider (or a TilemapCollider2D) that is not a trigger, and `dynamic` with a dynamic Rigidbody2D as well.
- **Prefabs**: instances are unpacked from their `.prefab` files, with overrides of position, scale, active, sprite, sorting order, enabled, trigger and body type, nested prefabs and variants.
- **Said, not hidden**: what is left out (rotation, flipped tiles, hexagonal grids, objects off the grid or not cell-sized, sprites or prefabs that were not found, later frames of an animation) is listed in a dialog after the import.
- Lights and effects are not imported (a level made this way starts with Stride2D's defaults); add them in the Lights and Effects windows.

Not yet: generating the player's C#/C from the GUI, WASM window.

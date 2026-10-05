# Stride2D

A small 2D game engine whose games are written in C# and ship as **one native executable with no .NET in it**.

The engine and the game are written in a restricted subset of C#. A translator ([CCSharp](https://github.com/crustos/CCSharp)) turns them into a single C file, and an ordinary C compiler builds that. The same source also runs on .NET, which is the reference: every test and sample is built both ways and must print exactly the same thing.

It started as a fork of [Stride](https://github.com/stride3d/stride). The engine in `src/` is now a different, much smaller design, derived from the 2D runtime of [Prowl](https://github.com/crustos/Prowl). Stride's original sources are still in `sources/`, for reference only: nothing here builds or depends on them.

## What works

| | |
|---|---|
| **Scene** | Nodes and components, scripts with Unity-style callbacks, a fixed-step loop |
| **Physics** | [Box2D](https://github.com/crustos/box2d) (the crustos fork): rigidbodies; box, circle and convex polygon colliders; collision and trigger events; overlap queries; forces and impulses |
| **Destructible terrain** | A port of [DTerrain](https://github.com/crustos/DTerrain): a pixel bitmap you can dig and build, with box or smooth one-sided chain colliders, rebuilt per chunk, and a dirty rectangle for the renderer |
| **Shattering sprites** | A port of [Unity-2D-Destruction](https://github.com/crustos/Unity-2D-Destruction): break a box or convex polygon into Voronoi or Delaunay fragments, each a rigidbody with a polygon collider and a textured mesh; explosion forces |
| **Draw data** | Sprite instances, mesh triangle lists and the terrain's dirty rectangle, ready for a renderer |
| **Scripts outside the subset** | Optional: a script that uses lambdas, `try/catch` or LINQ runs on [DotNetAnywhere](https://github.com/crustos/DotNetAnywhere), while the engine stays native |

## What does not exist yet

- **No window, renderer, textures, input or audio.** The engine produces draw data; nothing consumes it yet. Everything runs headless.
- **Terrain raises no collision events.** Terrain shapes carry no collider id, so contacts with them are not reported (contacts between fragments and other bodies are).
- **Shattering needs a convex outline.** A concave one is refused.
- **3D objects drawn in front of or behind 2D layers** is planned, not built.
- Tested on Linux x86-64 (Ubuntu 24.04) only.

## Quick start

You need `python3`, `git`, `cmake`, a C compiler and the .NET SDK (for the translator and the .NET reference build only; it is not in what you ship). Tested with .NET 10.

```sh
git clone https://github.com/crustos/stride2D.git
cd stride2D
python3 build.py deps        # clones box2d, CCSharp (+ crust, coost) next to this repo
python3 build.py native      # builds Box2D and the shim
python3 build.py ccsharp     # builds the translator
python3 build.py player samples/Headless2D --verify --run
```

That translates the sample to C, builds `build/player/Headless2D/stride2d-player`, runs it, then runs the same source on .NET and checks that both print the same thing.

Then run everything:

```sh
python3 build.py test --sanitize --dna
```

This builds each folder of `tests/` and `samples/` natively, compares it with .NET, and runs it again under AddressSanitizer and UBSan. `--dna` needs [DotNetAnywhere](https://github.com/crustos/DotNetAnywhere) cloned beside this repo (`git clone https://github.com/crustos/DotNetAnywhere ../DotNetAnywhere`) and `mono-mcs` (`apt install mono-mcs`); without them, leave it out and the DotNetAnywhere sample is reported as outside the subset.

## `build.py`

| Command | |
|---|---|
| `deps` | Clone `../box2d` and `../CCSharp` (and its `crust`, `coost`) beside this repo |
| `native [--avx2]` | Build Box2D and the `pb2_*` shim into `build/box2d` |
| `ccsharp` | Build the translator |
| `dotnet GAME` | Run a game on .NET: the reference |
| `check GAME [--dna]` | Does it translate to C? Prints what is outside the subset, with file and line |
| `player GAME [--verify] [--static] [--run] [--dna]` | Translate, build the native player, optionally compare with .NET |
| `test [--sanitize] [--dna] [NAME..]` | Every test and sample: native against .NET |
| `bench [--avx2] [--cachegrind]` | Native physics benchmark; prints a state hash that must not change |
| `status`, `clean` | Show what is installed; remove `build/` |

`GAME` is any folder of `.cs` files with a static `Main`.

## Writing a game

A script is a class marked `[Script]`. The engine calls it by name: `Start`, `Update`, `FixedUpdate`, `LateUpdate`, `OnEnable`, `OnDisable`, `OnCollisionBegin2D`, `OnCollisionEnd2D`, `OnTriggerEnter2D`, `OnTriggerStay2D`, `OnTriggerExit2D`. This is `samples/Headless2D` (trimmed): a ball dropped on a floor.

```csharp
using System;
using Stride2D;
using Stride2D.Native.Box2D;

[Script, MaxInstances(4)]
class Ball
{
    public Component Self;
    public int Hits;

    public void Reset() { Hits = 0; }

    public void OnCollisionBegin2D(Collision2D hit)
    {
        Hits++;
        Console.WriteLine("hit " + Hits + " normalY*1000=" + (int)(hit.NY * 1000f));
    }
}

static class Game
{
    public static int Main()
    {
        Scripts.Init();
        Scene2D scene = new Scene2D();

        Node ground = scene.NewNode(null);
        ground.SetPosition(0f, -0.5f);
        scene.AddBoxCollider(ground, 100f, 1f);          // no rigidbody: static; its top is at y = 0

        Node ball = scene.NewNode(null);
        ball.SetPosition(0f, 5f);
        scene.AddRigidbody(ball, PB2.BodyDynamic);
        scene.AddCircleCollider(ball, 0.5f);
        Ball script = Scripts.AddBall(ball);

        for (int frame = 0; frame < 240; frame++)
            Scripts.Tick(scene, 1f / 60f);

        return script.Hits >= 1 ? 0 : 1;
    }
}
```

`Scripts` is generated at build time from your `[Script]` classes (`tools/gen_scripts.py`). Terrain and shattering are in `samples/Terrain2D` and `samples/Destruction2D`. In outline (`using Stride2D.Terrain; using Stride2D.Destruction;`):

```csharp
// destructible terrain: 64 x 32 pixels, 8 pixels per unit, in 2 x 1 chunks, with box colliders
TerrainLayer ground = new TerrainLayer(scene, 64, 32, 2, 1, 8f, 0f, 0f, TerrainLayer.Boxes);
// ... ground.SetPixel(x, y, r, g, b, a) to fill the bitmap ...
ground.Build();

Shape crater = Shape.GenerateShapeCircle(8);
ground.Paint(crater, 24, 4, true, 0, 0, 0);     // dig; call ground.Update() once a frame, before the step

// a shattering crate: a box (or convex polygon) collider and a rigidbody on the node
Destruction2D boom = new Destruction2D(scene, 42u);
ExplodeOptions options = new ExplodeOptions();
options.Mode = Fracturer.Voronoi;
int fragments = boom.Explode(crate, options);   // the crate becomes fragments, each with its own body and mesh
boom.AddExplosionForce(x, y, 3f, 5f, 0f);       // push them away from (x, y)
```

## The C# subset

The translator accepts a subset of C#, and `build.py check GAME` says exactly what it refuses and where. The rules you will meet first:

- **A class is a single-owner value.** You cannot alias one (`Column c = columns[i]`), compare it with `==`, or give it `null`. Read through the owner (`columns[i].Touches(...)`).
- **Arena classes are the exception.** A class marked `[MaxInstances(N)]` lives in a pool of N slots allocated once, and may be referenced, compared and null. Nodes, components and scripts are arenas; so are `TerrainLayer`, `TerrainChunk` and `Destruction2D`. When a pool is full, creating one through the scene returns `null`, so check.
- **No delegates, lambdas, LINQ or `try/catch`.** Use `--dna` for a script that needs them.
- **Build strings on their own line** when another part of the statement calls something with a side effect.

Things the translator does not handle yet, which the engine works around and you may meet in your own code: a list element passed straight into a call that also takes a list, a nested index such as `a[b[i]]`, `out` parameters of struct type, and a call to a static class from inside a struct method. If the generated C fails with "subscripted value is neither array nor pointer", read the element into a local first.

### Limits

Pools are fixed at build time (`src/core/CoreLimits.cs`, `src/physics/`, `src/terrain/TerrainLimits.cs`).

| Pool | Size | Pool | Size |
|---|---|---|---|
| Nodes | 256 | Meshes | 256 |
| Components | 512 | Native bodies | 256 |
| Rigidbodies | 128 | Joints | 64 |
| Colliders | 256 | Terrain layers / chunks | 4 / 64 |
| Sprites | 256 | Points in one terrain chain | 4096 |

`Destruction2D.Explode` stops cleanly when a pool runs out, keeps the fragments it made, and reports how many it wanted in `Requested`.

## Layout

| | |
|---|---|
| `src/core/` | Scene, nodes, components, sprite and mesh renderers, the physics world |
| `src/physics/` | The simulation core and its registry |
| `src/native/box2d/` | The C shim over Box2D (`pb2_*`) and its CMake |
| `src/terrain/` | Destructible terrain |
| `src/destruction/` | Shattering and explosions |
| `tools/` | `player_build.py` (translate, build, verify), `gen_scripts.py`, `gen_pb2.py` |
| `tests/`, `samples/` | Headless programs that print what they do; they double as the test suite |
| `bench/` | The native physics benchmark |
| `Stride2D.csproj` | The one list of runtime source files, used by the .NET and the C build |
| `sources/` | Stride's original sources, for reference only |

## Credits and licenses

MIT, see [LICENSE.md](LICENSE.md). Built on:

- [Stride](https://github.com/stride3d/stride): where this fork started.
- [Prowl](https://github.com/crustos/Prowl) (Michael Sakharov): the 2D runtime in `src/core`, `src/physics` and `src/native/box2d` is derived from it.
- [Box2D](https://github.com/crustos/box2d) (Erin Catto): the physics, through the crustos fork.
- [DTerrain](https://github.com/crustos/DTerrain) (Dominik Zimny): `src/terrain` is ported from it.
- [Unity-2D-Destruction](https://github.com/crustos/Unity-2D-Destruction) (Matthew Holtzem): `src/destruction` is ported from it.
- [CCSharp](https://github.com/crustos/CCSharp), [DotNetAnywhere](https://github.com/crustos/DotNetAnywhere), crust and coost: the translator and the optional managed runtime, cloned beside this repo at build time; see their repositories for their licenses.

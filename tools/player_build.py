#!/usr/bin/env python3
"""player_build.py -- turn a game written against the Stride2D runtime into a native executable with no .NET in it.

    python3 tools/player_build.py GAME_DIR [-o OUT] [--check] [--verify] [--static] [--run]

GAME_DIR holds the game's C# files: scripts (classes marked [Script]) and one class with a static Main. Steps:
  1. generate the call sink for the scripts (gen_scripts.py) and both flavors of the native bindings (gen_pb2.py);
  2. translate runtime + game + sink to ONE C file with CCSharp (the only step that needs .NET: CCSharp is built on Roslyn);
  3. build it with a C compiler against libstride2d_box2d_static.a and libbox2d.a (from `python3 build.py native`).
--check   stop after step 2 and print what is outside the C# subset as `File.cs(line,col): error CCS0001: ...`
--verify  also run the game on .NET (the reference) and require the same output
--static  link a fully static executable (no loader, no libc.so)
--wasm    build for WebAssembly (wasm32-wasi): OUT/stride2d-player.wasm and a launcher OUT/stride2d-player that runs it under node 20+ (with run_wasm.mjs, the
          host, from DotNetAnywhere). Box2D and the shim are compiled for wasm32 first (build/wasm32). With --verify the output is compared with the .NET run too.
          Combines with --dna (the managed classes run on DotNetAnywhere compiled to wasm, with its JIT). Not with --static or --sanitize.
--dna     a class the C build cannot translate (a script that uses a lambda, try/catch, LINQ ...) runs on DotNetAnywhere instead of being refused,
          together with the classes that use it; the engine stays native and the managed side reaches its objects by address. Needs DotNetAnywhere
          (../DotNetAnywhere) and mono-mcs. The player then needs player.managed.dll and corlib.dll beside it.
"""
import argparse, os, re, shutil, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import gen_pb2      # noqa: E402
import gen_scripts  # noqa: E402

BUILD = os.path.join(ROOT, "build")
NATIVE_DIR = os.path.join(BUILD, "box2d")
BOX2D_LIB = os.path.join(NATIVE_DIR, "box2d", "src", "libbox2d.a")
SHIM_A = os.path.join(NATIVE_DIR, "libstride2d_box2d_static.a")
SHIM_H = os.path.join(ROOT, "src", "native", "box2d", "box2d_shim.h")


def sibling(name):
    return os.path.join(os.path.dirname(ROOT), name)


def ccs2c_path():
    home = os.environ.get("CCSHARP_HOME") or sibling("CCSharp")
    return os.path.join(home, "crust", "ccs2c.py")


def ccs2c_module():
    """crust/ccs2c.py loaded as a module: it holds the DotNetAnywhere build (dna_prepare, dna_run) that --dna uses."""
    import importlib.util
    path = ccs2c_path()
    here = os.path.dirname(path)
    if here not in sys.path:
        sys.path.insert(0, here)                 # ccs2c imports its siblings (inputs, unit) by name
    spec = importlib.util.spec_from_file_location("ccs2c", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


FEATURES = {"terrain": "Stride2D.Terrain", "destruction": "Stride2D.Destruction"}     # a Feature="x" item of Stride2D.csproj is in a game that mentions this namespace


def runtime_files(game=None):
    """The runtime's C# files, from Stride2D.csproj (the one list). CBuild="false" items are left out; Feature="x" items
    are in only if one of the game's files mentions the feature's namespace."""
    proj = os.path.join(ROOT, "Stride2D.csproj")
    text = open(proj, encoding="utf-8").read()
    used = set()
    for name, ns in FEATURES.items():
        for p in (game or []):
            if ns in open(p, encoding="utf-8-sig").read():
                used.add(name)
                break
    out = []
    for m in re.finditer(r'<Compile\s+Include="([^"]+)"([^>]*)/>', text):
        attrs = m.group(2)
        if 'CBuild="false"' in attrs:
            continue
        f = re.search(r'Feature="(\w+)"', attrs)
        if f and f.group(1) not in used:
            continue
        out.append(os.path.normpath(os.path.join(ROOT, m.group(1).replace("\\", os.sep))))
    return out


def game_files(d):
    out = []
    for dp, dn, fn in os.walk(d):
        dn[:] = [x for x in dn if x not in ("obj", "bin", "generated")]
        out += [os.path.join(dp, f) for f in sorted(fn) if f.endswith(".cs") and not f.endswith(".g.cs")]
    return sorted(out)


def find_frame_class(files):
    """For --web: the class with a static Init() and a static Frame() (what a page drives), instead of one with Main."""
    for p in files:
        text = open(p, encoding="utf-8-sig").read()
        if re.search(r"\bstatic\s+(?:int|void)\s+Init\s*\(\s*\)", text) and re.search(r"\bstatic\s+void\s+Frame\s*\(\s*\)", text):
            m = re.search(r"\bclass\s+(\w+)", text)
            ns = re.search(r"^\s*namespace\s+([\w.]+)", text, re.M)
            return (ns.group(1) + "." if ns else "") + m.group(1)
    return None


def find_main(files):
    for p in files:
        text = re.sub(r"//[^\n]*", "", open(p, encoding="utf-8-sig").read())
        m = re.search(r"\bstatic\s+(?:int|void)\s+Main\s*\(", text)
        if not m:
            continue
        classes = [c for c in re.finditer(r"\bclass\s+(\w+)", text) if c.start() < m.start()]
        if classes:
            ns = re.search(r"^\s*namespace\s+([\w.]+)", text, re.M)
            return (ns.group(1) + "." if ns else "") + classes[-1].group(1)
    return None


_REFUSAL = re.compile(r"^(?P<file>/\S+?\.cs):(?P<line>\d+): (?P<msg>.+)$")
_ROSLYN = re.compile(r"^(?P<file>.+?\.cs): \((?P<line>\d+),(?P<col>\d+)\): error (?P<code>CS\d+): (?P<msg>.*)$")


def diagnostics(text):
    out = []
    for line in text.splitlines():
        m = _ROSLYN.match(line.strip())
        if m:
            out.append("%s(%s,%s): error %s: %s" % (m["file"], m["line"], m["col"], m["code"], m["msg"]))
            continue
        m = _REFUSAL.match(line.strip())
        if m:
            out.append("%s(%s,1): error CCS0001: not in the C build's C# subset: %s" % (m["file"], m["line"], m["msg"]))
    return out


GFX_H = os.path.join(ROOT, "src", "native", "gfx2d", "gfx2d.h")


def uses_gfx(game):
    """True if a game file mentions the renderer's namespace: then the gfx2d bindings are generated and libgfx2d is linked."""
    return any("Stride2D.Native.Gfx2D" in open(p, encoding="utf-8-sig").read() for p in game)


def generate_bindings(out_dir, gfx):
    """Both flavors of the Box2D bindings and, when the game draws, of the renderer's. Both sets are files of one folder (GFX.*.cs beside PB2.*.cs)."""
    try:
        gen_pb2.use("box2d")
        gen_pb2.generate(out_dir)
        if gfx:
            gen_pb2.use("gfx2d")
            m = gen_pb2.generate(out_dir)
            have = next((c[1] for c in m.consts if c[0] == "GFX_SPRITE_FLOATS"), None)
            limit = re.search(r"SpriteFloats\s*=\s*(\d+)", open(os.path.join(ROOT, "src", "core", "CoreLimits.cs"), encoding="utf-8").read())
            if have is not None and limit and int(have) != int(limit.group(1)):
                sys.exit("player_build: GFX_SPRITE_FLOATS (%s) != CoreLimits.SpriteFloats (%s)" % (have, limit.group(1)))
    finally:
        gen_pb2.use("box2d")


def gfx_library(wasm=False):
    """Path of libgfx2d_static.a for the native player (built on demand)."""
    import gfx_build
    return gfx_build.build(quiet=True)["static"]


def generate_only(game, out_dir):
    """Bindings (both flavors) and the script sink, without translating: what the .NET reference needs."""
    gen = os.path.join(out_dir, "generated")
    shutil.rmtree(gen, ignore_errors=True)
    os.makedirs(gen)
    generate_bindings(os.path.join(gen, "bindings"), uses_gfx(game))
    gen_scripts.generate(os.path.join(gen, "Scripts.g.cs"), game)


def translate(game, out_dir, main_class, dna=False):
    gen = os.path.join(out_dir, "generated")
    inc = os.path.join(gen, "include")
    shutil.rmtree(gen, ignore_errors=True)
    os.makedirs(inc)
    generate_bindings(os.path.join(gen, "bindings"), uses_gfx(game))
    shutil.copy2(SHIM_H, inc)
    if uses_gfx(game):
        shutil.copy2(GFX_H, inc)
    sink = os.path.join(gen, "Scripts.g.cs")
    gen_scripts.generate(sink, game)
    c_dir = os.path.join(out_dir, "c")
    shutil.rmtree(c_dir, ignore_errors=True)
    # the C flavor of the bindings holds no code (extern members with [Cpp] templates), so it is an ordinary input
    bindings = [os.path.join(gen, "bindings", "c", n) for n in sorted(os.listdir(os.path.join(gen, "bindings", "c")))]
    cmd = ([sys.executable, ccs2c_path()] + bindings + runtime_files(game) + game + [sink]
           + ["--main=" + main_class, "--name=player", "--convert=" + c_dir, "--c"] + (["--dna"] if dna else []))
    r = subprocess.run(cmd, capture_output=True, text=True)
    raw = r.stdout + r.stderr
    c_file = os.path.join(c_dir, "player.c")
    if r.returncode != 0 or not os.path.exists(c_file):
        return None, diagnostics(raw), raw
    return c_file, [], raw


def package_and_build_dna(out_dir, c_dir, cc):
    """The hybrid player: the translated C, the glue that calls DotNetAnywhere, the runtime with the native functions the managed side may call
    in its FFI table, and the Box2D shim. The managed assembly and corlib.dll go beside it."""
    ccs = ccs2c_module()
    try:
        home, bdir = ccs.dna_prepare()
    except Exception as e:                      # ccs2c's Refused: DotNetAnywhere or mono-mcs missing, or its build failed
        sys.exit("player_build: " + str(e))
    for need in (SHIM_A, BOX2D_LIB):
        if not os.path.exists(need):
            sys.exit("player_build: %s is missing (python3 build.py native)" % need)
    glue = os.path.join(c_dir, "player.bridge.c")
    if not os.path.exists(glue):                                    # nothing was managed: an ordinary player
        return None
    manifest = os.path.join(c_dir, "player.ffi.json")
    if os.path.exists(manifest):
        ccs.dna_run(["--ffi", manifest, "--lib-only", "--no-corlib"], home, bdir)
        lib = os.path.join(bdir, "libdna_ffi.a")
    else:
        lib = os.path.join(bdir, "libdna.a")
    shutil.copy2(os.path.join(c_dir, "player.c"), os.path.join(out_dir, "player.c"))
    shutil.copy2(glue, os.path.join(out_dir, "player.bridge.c"))
    shutil.copy2(SHIM_H, os.path.join(out_dir, "box2d_shim.h"))
    os.makedirs(os.path.join(out_dir, "lib"), exist_ok=True)
    shutil.copy2(SHIM_A, os.path.join(out_dir, "lib", "libstride2d_box2d_static.a"))
    shutil.copy2(BOX2D_LIB, os.path.join(out_dir, "lib", "libbox2d.a"))
    shutil.copy2(lib, os.path.join(out_dir, "lib", "libdna.a"))
    shutil.copy2(os.path.join(c_dir, "player.managed.dll"), out_dir)
    shutil.copy2(os.path.join(bdir, "corlib.dll"), out_dir)
    exe = os.path.join(out_dir, "stride2d-player")
    if os.path.exists(exe):
        os.remove(exe)
    cmd = [cc, "-O2", "-ffp-contract=off", "-w", "-I.", "-I", os.path.join(home, "native", "src"), "-o", "stride2d-player", "player.c", "player.bridge.c",
           "-Llib", "-lstride2d_box2d_static", "-lbox2d", "lib/libdna.a", "-lm", "-lpthread"]
    g = subprocess.run(cmd, cwd=out_dir, capture_output=True, text=True)
    if g.returncode != 0:
        errs = [l for l in g.stderr.splitlines() if "error" in l or "undefined" in l]
        sys.exit("player_build: the C compiler rejected the hybrid player:\n   " + "\n   ".join(e[:200] for e in errs[:8]))
    return exe


def package_and_build(out_dir, c_file, cc, static, gfx=False):
    for need in (SHIM_A, BOX2D_LIB):
        if not os.path.exists(need):
            sys.exit("player_build: %s is missing (python3 build.py native)" % need)
    shutil.copy2(c_file, os.path.join(out_dir, "player.c"))
    shutil.copy2(SHIM_H, os.path.join(out_dir, "box2d_shim.h"))
    os.makedirs(os.path.join(out_dir, "lib"), exist_ok=True)
    shutil.copy2(SHIM_A, os.path.join(out_dir, "lib", "libstride2d_box2d_static.a"))
    shutil.copy2(BOX2D_LIB, os.path.join(out_dir, "lib", "libbox2d.a"))
    extra = ""
    if gfx:
        shutil.copy2(GFX_H, os.path.join(out_dir, "gfx2d.h"))
        shutil.copy2(gfx_library(), os.path.join(out_dir, "lib", "libgfx2d_static.a"))
        extra = " -lgfx2d_static -ldl"       # the renderer loads EGL / GLES / X11 with dlopen: libdl and libm are all it links
    with open(os.path.join(out_dir, "Makefile"), "w", newline="\n") as f:
        f.write("# Builds the player from the translated C. Needs a C compiler and nothing else: no .NET, no CMake.\n"
                "CC ?= cc\nCFLAGS ?= -O2 -ffp-contract=off -w\n"
                "LIBS = -Llib -lstride2d_box2d_static -lbox2d%s -lm\n\n" % extra +
                "stride2d-player: player.c box2d_shim.h lib/libstride2d_box2d_static.a lib/libbox2d.a\n"
                "\t$(CC) $(CFLAGS) -I. -o $@ player.c $(LIBS)\n\n"
                "static: player.c box2d_shim.h lib/libstride2d_box2d_static.a lib/libbox2d.a\n"
                "\t$(CC) $(CFLAGS) -static -I. -o stride2d-player player.c $(LIBS)\n\n"
                "clean:\n\trm -f stride2d-player\n\n.PHONY: static clean\n")
    exe = os.path.join(out_dir, "stride2d-player")
    if os.path.exists(exe):
        os.remove(exe)
    cmd = [cc, "-O2", "-ffp-contract=off", "-w", "-I.", "-o", "stride2d-player", "player.c",
           "-Llib", "-lstride2d_box2d_static", "-lbox2d"] + (["-lgfx2d_static", "-ldl"] if gfx else []) + ["-lm"]
    if static:
        cmd.insert(1, "-static")
    g = subprocess.run(cmd, cwd=out_dir, capture_output=True, text=True)
    if g.returncode != 0:
        errs = [l for l in g.stderr.splitlines() if "error" in l or "undefined" in l]
        sys.exit("player_build: the C compiler rejected the translated C:\n   " + "\n   ".join(e[:200] for e in errs[:8]))
    return exe


def sanitize_run(out_dir, cc, expected_stdout):
    """Builds the translated C again with AddressSanitizer and UBSan and runs it. Returns None if clean, else what went wrong.
    (Leak detection is off: arena classes live until the process ends by design, and LeakSanitizer discards buffered output.)"""
    exe = os.path.join(out_dir, "player_asan")
    cmd = [cc, "-O1", "-g", "-w", "-fsanitize=address,undefined", "-fno-omit-frame-pointer", "-I.", "-o", "player_asan", "player.c",
           "-Llib", "-lstride2d_box2d_static", "-lbox2d", "-lm"]
    b = subprocess.run(cmd, cwd=out_dir, capture_output=True, text=True)
    if b.returncode != 0:
        return "the sanitizer build failed: " + b.stderr[-300:]
    env = dict(os.environ, ASAN_OPTIONS="detect_leaks=0", UBSAN_OPTIONS="print_stacktrace=1")
    r = subprocess.run([exe], cwd=out_dir, capture_output=True, text=True, env=env)
    bad = [l for l in r.stderr.splitlines() if "ERROR: AddressSanitizer" in l or "runtime error" in l]
    if bad:
        return "%d report(s): %s" % (len(bad), bad[0][:200])
    if r.stdout != expected_stdout:
        return "output differs under the sanitizers"
    return None


def run_dotnet_reference(game, out_dir):
    gen = os.path.join(out_dir, "generated")
    nets = [os.path.join(gen, "bindings", "net", n) for n in sorted(os.listdir(os.path.join(gen, "bindings", "net")))]
    files = nets + runtime_files(game) + game + [os.path.join(gen, "Scripts.g.cs")]
    work = os.path.join(out_dir, "dotnet-reference")
    shutil.rmtree(work, ignore_errors=True)
    os.makedirs(work)
    proj = os.path.join(work, "ref.csproj")
    items = "\n".join('    <Compile Include="%s" />' % f for f in files)
    with open(proj, "w") as f:
        f.write('<Project Sdk="Microsoft.NET.Sdk">\n  <PropertyGroup><OutputType>Exe</OutputType><TargetFramework>net10.0</TargetFramework>'
                '<ImplicitUsings>disable</ImplicitUsings><Nullable>disable</Nullable><NuGetAudit>false</NuGetAudit>'
                '<AllowUnsafeBlocks>true</AllowUnsafeBlocks><EnableDefaultCompileItems>false</EnableDefaultCompileItems></PropertyGroup>\n'
                '  <ItemGroup>\n%s\n  </ItemGroup>\n</Project>\n' % items)
    env = dict(os.environ, DOTNET_CLI_TELEMETRY_OPTOUT="1", DOTNET_NOLOGO="1",
               LD_LIBRARY_PATH=NATIVE_DIR + os.pathsep + os.environ.get("LD_LIBRARY_PATH", ""))
    b = subprocess.run(["dotnet", "build", "-c", "Release", "-o", os.path.join(work, "bin"), proj], capture_output=True, text=True, env=env)
    if b.returncode != 0:
        return None, "the reference did not build under .NET:\n" + "\n".join(l for l in b.stdout.splitlines() if "error" in l)[:1500]
    r = subprocess.run(["dotnet", os.path.join(work, "bin", "ref.dll")], capture_output=True, text=True, env=env)
    return (r.stdout, r.returncode), None


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("game")
    ap.add_argument("-o", "--out")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--verify", action="store_true")
    ap.add_argument("--static", action="store_true")
    ap.add_argument("--cc", default=os.environ.get("CC") or "cc")
    ap.add_argument("--run", action="store_true")
    ap.add_argument("--sanitize", action="store_true", help="also run the translated C under AddressSanitizer and UBSan")
    ap.add_argument("--dotnet", action="store_true", help="only run the game on .NET (the reference); no translation")
    ap.add_argument("--dna", action="store_true", help="run what the C build cannot translate on DotNetAnywhere (see above)")
    ap.add_argument("--wasm", action="store_true", help="build for WebAssembly (wasm32-wasi), run under node")
    ap.add_argument("--web", action="store_true", help="build a browser page (WebGL2 / WebGPU): the game has static Init() and Frame() instead of Main; implies --wasm")
    a = ap.parse_args()

    if a.web: a.wasm = True
    game_dir = os.path.abspath(a.game)
    files = game_files(game_dir)
    if not files:
        sys.exit("player_build: no .cs files in %s" % game_dir)
    main_class = find_main(files) if not a.web else find_frame_class(files)
    if not main_class:
        sys.exit("player_build: no class with a static Main in %s" % game_dir)
    if not os.path.exists(ccs2c_path()):
        sys.exit("player_build: CCSharp not found at %s (python3 build.py deps)" % ccs2c_path())
    name = os.path.basename(game_dir.rstrip(os.sep))
    if a.web and not uses_gfx(files):
        sys.exit("player_build: --web: the game does not use Stride2D.Native.Gfx2D, so there is nothing for a page to draw")
    out_dir = os.path.abspath(a.out or os.path.join(BUILD, "player", name + ("-web" if a.web else "-wasm" if a.wasm else "")))
    os.makedirs(out_dir, exist_ok=True)
    if a.wasm:
        import wasm_build
        ok, why = wasm_build.available()
        if not ok:
            sys.exit("player_build: --wasm: " + why)
        if a.static or a.sanitize:
            sys.exit("player_build: --static and --sanitize are for the native player; --wasm builds a wasm module")
    if a.dotnet:
        generate_only(files, out_dir)
        ref, err = run_dotnet_reference(files, out_dir)
        if ref is None:
            print(err)
            return 1
        print(ref[0])
        print("exit code %d" % ref[1])
        return ref[1]
    print("game      %s  (%d file%s, entry %s)" % (os.path.relpath(game_dir, ROOT), len(files), "" if len(files) == 1 else "s", main_class))
    try:
        c_file, diags, raw = translate(files, out_dir, main_class, a.dna)
    except gen_scripts.GenError as e:
        print("%s: error CCS0002: %s" % (game_dir, e))
        return 1
    if c_file is None:
        if diags:
            print("\n".join(diags))
            print("\n%d construct(s) outside the C# subset: the C build cannot translate this game." % len(diags))
        else:
            print("player_build: the translator failed:\n" + raw[-1500:])
        return 1
    print("translated  %s  (%d lines of C)" % (os.path.relpath(c_file, ROOT), sum(1 for _ in open(c_file))))
    managed = []
    if a.dna:
        import json
        with open(os.path.join(os.path.dirname(c_file), "player.partition.json")) as f:
            part = json.load(f)
        managed = [c for c in part["classes"] if c["partition"] == "managed"]
        native = [c for c in part["classes"] if c["partition"] == "native"]
        if managed:
            print("hybrid      %d class(es) native, %d on DotNetAnywhere: %s" % (len(native), len(managed), ", ".join(c["name"].split(".")[-1] for c in managed)))
            for c in managed:
                why = c["reason"].replace(ROOT + os.sep, "")
                print("            %-12s %s" % (c["name"].split(".")[-1], why if len(why) < 150 else why[:147] + "..."))
    if a.check:
        print("ok: the game %s" % ("is inside the C# subset" if not managed else "translates; %d class(es) run on DotNetAnywhere" % len(managed)))
        return 0
    c_dir = os.path.dirname(c_file)
    if a.wasm:
        shutil.copy2(SHIM_H, os.path.join(out_dir, "box2d_shim.h"))
        if a.dna and os.path.exists(os.path.join(c_dir, "player.bridge.c")):
            exe, module = wasm_build.link_hybrid(out_dir, c_dir, a.cc if a.cc != "cc" else None)
            kind = "hybrid: native C + managed on DotNetAnywhere, wasm32"
        elif a.web:
            shutil.copy2(c_file, os.path.join(out_dir, "player.c"))
            shutil.copy2(GFX_H, os.path.join(out_dir, "gfx2d.h"))
            module = wasm_build.link_web(out_dir, main_class)
            print("built       %s  (%d KiB; a page: serve %s over http://localhost and open index.html, ?gfx=webgl2 or ?gfx=webgpu)" % (
                os.path.relpath(module, ROOT), os.path.getsize(module) // 1024, os.path.relpath(out_dir, ROOT)))
            return 0
        else:
            shutil.copy2(c_file, os.path.join(out_dir, "player.c"))
            exe, module = wasm_build.link_player(out_dir)
            kind = "wasm32"
        print("built       %s  (%d KiB; %s; run it with %s, which needs node 20+)" % (os.path.relpath(module, ROOT), os.path.getsize(module) // 1024, kind,
                                                                                 os.path.relpath(exe, ROOT)))
    else:
        exe = package_and_build_dna(out_dir, c_dir, a.cc) if a.dna else None
        if exe is None:
            exe = package_and_build(out_dir, c_file, a.cc, a.static, uses_gfx(files))
        print("built       %s  (%d KiB)" % (os.path.relpath(exe, ROOT), os.path.getsize(exe) // 1024))
    nat = subprocess.run([exe], capture_output=True, text=True, cwd=out_dir)
    rc = 0
    if nat.returncode != 0:
        print("the player exited with %d" % nat.returncode)
        rc = 1
    if a.sanitize and managed:
        print("sanitize  skipped: a hybrid player (with DotNetAnywhere) is not run under the sanitizers")
    elif a.sanitize:
        why = sanitize_run(out_dir, a.cc, nat.stdout)
        if why is None:
            print("sanitize  ok: no AddressSanitizer or UBSan reports")
        else:
            print("sanitize  FAILED: " + why)
            rc = 1
    if a.run or a.verify:
        print("\n" + nat.stdout)
    if a.verify:
        ref, err = run_dotnet_reference(files, out_dir)
        if ref is None:
            print("verify    FAILED to run the .NET reference: %s" % err)
            return 1
        text, code = ref
        if text == nat.stdout and code == nat.returncode:
            print("verify    ok: %s and .NET print identical output (%d lines) and exit with the same code (%d)" % ("the wasm module" if a.wasm else "native", len(text.splitlines()), code))
        else:
            x, y = text.splitlines(), nat.stdout.splitlines()
            first = next((i for i in range(max(len(x), len(y))) if i >= len(x) or i >= len(y) or x[i] != y[i]), -1)
            print("verify    FAILED: exit codes .NET=%d native=%d; first differing line: %d\n   .NET  : %s\n   native: %s"
                  % (code, nat.returncode, first + 1, x[first] if 0 <= first < len(x) else "(none)", y[first] if 0 <= first < len(y) else "(none)"))
            rc = 1
    return rc


if __name__ == "__main__":
    sys.exit(main())

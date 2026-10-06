#!/usr/bin/env python3
"""wasm_build.py -- the WebAssembly (wasm32-wasi) half of `python3 build.py player GAME --wasm`.

Box2D-Packed and the pb2_* shim are compiled with clang for wasm32-wasi into two archives (build/wasm32/), and the translated player.c is linked with
them into one module, run under node (WASI) by the host script CCSharp's --wasm already uses (DotNetAnywhere's tools/run_wasm.mjs).

Box2D is built without SIMD (BOX2D_DISABLE_SIMD, the scalar path): Box2D v3 is deterministic across its SIMD paths, so the native player (SSE2) and
this one print the same thing. -ffp-contract=off is as in the native build.
"""
import glob
import os
import re
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
OUT = os.path.join(ROOT, "build", "wasm32")
SHIM_DIR = os.path.join(ROOT, "src", "native", "box2d")
NAME = "stride2d-player"


def _ccs2c():
    sys.path.insert(0, os.path.join(os.environ.get("CCSHARP_HOME") or os.path.join(os.path.dirname(ROOT), "CCSharp"), "crust"))
    import ccs2c
    return ccs2c


def box2d_dir():
    return os.environ.get("BOX2D_HOME") or os.path.join(os.path.dirname(ROOT), "box2d")


def available():
    """(True, "") when this machine can build for wasm32-wasi (and CCSharp is new enough to have --wasm), else (False, why)."""
    try:
        c = _ccs2c()
    except ImportError:
        return False, "no CCSharp beside this repository (python3 build.py deps)"
    if not hasattr(c, "wasm_available"):
        return False, "the CCSharp at %s has no --wasm (use a newer one)" % os.path.dirname(os.path.dirname(c.__file__))
    ok, why = c.wasm_available()
    if not ok:
        return False, why
    if not os.path.exists(os.path.join(box2d_dir(), "CMakeLists.txt")):
        return False, "Box2D-Packed is not at %s (python3 build.py deps)" % box2d_dir()
    return True, ""


def _cflags(c):
    return c._wasm_cflags() + ["-O2", "-ffp-contract=off", "-w", "-std=gnu17", "-DBOX2D_DISABLE_SIMD"]


def _compile(cc, flags, src, obj, incs):
    r = subprocess.run([cc] + flags + incs + ["-c", src, "-o", obj], capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit("wasm_build: clang rejected %s:\n%s" % (src, "\n".join(l for l in r.stderr.splitlines() if "error" in l)[:1500]))


def build_natives(force=False):
    """libbox2d.a and libstride2d_box2d_static.a for wasm32-wasi under build/wasm32. Returns the folder. Rebuilt when a source is newer."""
    c = _ccs2c()
    cc = c.wasm_compiler()
    box2d = box2d_dir()
    srcs = sorted(glob.glob(os.path.join(box2d, "src", "*.c")))
    shim = os.path.join(SHIM_DIR, "box2d_shim.c")
    heads = (glob.glob(os.path.join(box2d, "src", "*.h")) + glob.glob(os.path.join(box2d, "include", "box2d", "*.h"))
             + [os.path.join(SHIM_DIR, "box2d_shim.h")])
    libs = [os.path.join(OUT, "libbox2d.a"), os.path.join(OUT, "libstride2d_box2d_static.a")]
    newest = max(os.path.getmtime(p) for p in srcs + heads + [shim])
    if not force and all(os.path.exists(l) and os.path.getmtime(l) >= newest for l in libs):
        return OUT
    print("   wasm natives: Box2D-Packed (%d files) and the shim, clang --target=wasm32-wasi" % len(srcs))
    shutil.rmtree(os.path.join(OUT, "o"), ignore_errors=True)
    os.makedirs(os.path.join(OUT, "o", "b2"), exist_ok=True)
    os.makedirs(os.path.join(OUT, "o", "shim"), exist_ok=True)
    flags = _cflags(c)
    incs = ["-I" + os.path.join(box2d, "include"), "-I" + os.path.join(box2d, "src")]
    from concurrent.futures import ThreadPoolExecutor
    jobs = [(s, os.path.join(OUT, "o", "b2", os.path.basename(s)[:-2] + ".o")) for s in srcs]
    with ThreadPoolExecutor(max_workers=os.cpu_count() or 4) as ex:
        list(ex.map(lambda j: _compile(cc, flags, j[0], j[1], incs), jobs))
    shim_o = os.path.join(OUT, "o", "shim", "box2d_shim.o")
    _compile(cc, flags, shim, shim_o, incs)
    for lib, objs in ((libs[0], [j[1] for j in jobs]), (libs[1], [shim_o])):
        if os.path.exists(lib):
            os.remove(lib)
        subprocess.run(["llvm-ar", "rcs", lib] + objs, check=True)
    return OUT


def link_player(out_dir):
    """Links out_dir/player.c with the wasm archives into out_dir/stride2d-player.wasm, and writes the launcher stride2d-player and run_wasm.mjs beside
    it. Returns (launcher, module)."""
    c = _ccs2c()
    natives = build_natives()
    module = os.path.join(out_dir, NAME + ".wasm")
    if os.path.exists(module):
        os.remove(module)
    cmd = ([c.wasm_compiler()] + _cflags(c) + ["-I.", "-o", module, "player.c", "-L" + natives, "-lstride2d_box2d_static", "-lbox2d", "-lm"]
           + ["-fuse-ld=lld", "-Wl,-z,stack-size=8388608"])
    r = subprocess.run(cmd, cwd=out_dir, capture_output=True, text=True)
    if r.returncode != 0:
        errs = [l for l in r.stderr.splitlines() if "error" in l or "undefined" in l]
        sys.exit("player_build: clang (wasm32) rejected the translated C:\n   " + "\n   ".join(e[:200] for e in errs[:8]))
    launcher = os.path.join(out_dir, NAME)
    c._wasm_package(launcher, NAME, c.dna_home(), False)
    return launcher, module


def link_hybrid(out_dir, c_dir, cc=None):
    """A game with managed classes (--dna): the translated C, the glue that calls DotNetAnywhere, the DotNetAnywhere runtime (with the native functions
    the managed code may call in its FFI table), and Box2D, into out_dir/stride2d-player.wasm with its launcher. The managed assembly
    (player.managed.dll, the name the glue looks for) and corlib.dll are copied beside it. Returns the launcher."""
    c = _ccs2c()
    home, bdir = c.dna_prepare(True)
    manifest = os.path.join(c_dir, "player.ffi.json")
    if os.path.exists(manifest):
        c.dna_run(["--wasm", "--ffi", manifest, "--lib-only", "--no-corlib"], home, bdir)
        lib = os.path.join(bdir, "libdna_ffi_wasm.a")
    else:
        lib = os.path.join(bdir, "libdna_wasm.a")
    for f in ("player.c", "player.bridge.c", "player.managed.dll", "player.ffi.json"):
        if os.path.exists(os.path.join(c_dir, f)):
            shutil.copy2(os.path.join(c_dir, f), os.path.join(out_dir, f))
    shutil.copy2(os.path.join(bdir, "corlib.dll"), out_dir)
    natives = build_natives()
    module = os.path.join(out_dir, NAME + ".wasm")
    cmd = ([c.wasm_compiler(cc)] + _cflags(c) + ["-I.", "-I" + os.path.join(home, "native", "src"), "-o", module, "player.c", "player.bridge.c", lib,
                                                 "-L" + natives, "-lstride2d_box2d_static", "-lbox2d", "-lm"] + c._WASM_LDFLAGS)
    r = subprocess.run(cmd, cwd=out_dir, capture_output=True, text=True)
    if r.returncode != 0:
        errs = [l for l in (r.stdout + r.stderr).splitlines() if "error" in l or "undefined" in l]
        sys.exit("player_build: clang (wasm32) rejected the hybrid build:\n   " + "\n   ".join(e[:220] for e in errs[:10]))
    launcher = os.path.join(out_dir, NAME)
    c._wasm_package(launcher, "player", home, True)
    return launcher, module


GFX_DIR = os.path.join(ROOT, "src", "native", "gfx2d")


def _entry_points(c_text, main_class):
    """The C names of the game's static Init() and Frame() in the translated C: the definitions (at the start of a line, ending in `{`) whose name ends in
    Init / Frame and mentions the class. Returns (init_name, frame_name, init_returns_int)."""
    cls = main_class.split(".")[-1]
    found = {}
    for m in re.finditer(r"^(?:static\s+)?(\w+)\s+(\w*%s\w*?(Init|Frame))\s*\(\s*(?:void)?\s*\)\s*\{?\s*$" % re.escape(cls), c_text, re.M):
        found[m.group(3)] = (m.group(2), m.group(1))
    if "Init" not in found or "Frame" not in found:
        sys.exit("player_build: --web: %s needs `static int Init()` (or void) and `static void Frame()`; not found in the translated C" % cls)
    return found["Init"][0], found["Frame"][0], found["Init"][1] != "void"


def link_web(out_dir, main_class):
    """Links out_dir/player.c (a game with static Init() and Frame()) and the renderer's web backend as a WASI reactor, out_dir/stride2d-player.wasm, with the
    exports stride2d_init and stride2d_frame, and writes index.html and stride2d_web.js beside it (the page a browser opens). Returns the module path."""
    c = _ccs2c()
    natives = build_natives()
    init, frame, init_int = _entry_points(open(os.path.join(out_dir, "player.c"), encoding="utf-8").read(), main_class)
    entry = os.path.join(out_dir, "web_entry.c")
    with open(entry, "w", newline="\n") as f:
        f.write("// generated by tools/wasm_build.py: the two functions the page calls, around the game's Init() and Frame()\n"
                "int %s( void );\nvoid %s( void );\n" % (init, frame) if init_int else "void %s( void );\nvoid %s( void );\n" % (init, frame))
        f.write('__attribute__( ( export_name( "stride2d_init" ) ) ) int stride2d_init( void ) { %s; }\n' % ("return %s()" % init if init_int else "%s(); return 0" % init))
        f.write('__attribute__( ( export_name( "stride2d_frame" ) ) ) void stride2d_frame( void ) { %s(); }\n' % frame)
    module = os.path.join(out_dir, NAME + ".wasm")
    if os.path.exists(module):
        os.remove(module)
    # player.c has no main() to call: the page drives it, so it is a reactor and the translated main (if any) is unused
    cmd = ([c.wasm_compiler()] + _cflags(c) + ["-DGFX_HAVE_WEB=1", "-I.", "-I" + GFX_DIR, "-o", module, "player.c", "web_entry.c",
           os.path.join(GFX_DIR, "gfx2d_core.c"), os.path.join(GFX_DIR, "gfx2d_web.c"),
           "-L" + natives, "-lstride2d_box2d_static", "-lbox2d", "-lm"]
           + ["-fuse-ld=lld", "-mexec-model=reactor", "-Wl,--allow-undefined", "-Wl,-z,stack-size=8388608"])
    r = subprocess.run(cmd, cwd=out_dir, capture_output=True, text=True)
    if r.returncode != 0:
        errs = [l for l in r.stderr.splitlines() if "error" in l or "undefined" in l]
        sys.exit("player_build: clang (wasm32) rejected the web build:\n   " + "\n   ".join(e[:200] for e in errs[:8]))
    for f in ("index.html", "stride2d_web.js"):
        shutil.copy2(os.path.join(GFX_DIR, "web", f), out_dir)
    return module

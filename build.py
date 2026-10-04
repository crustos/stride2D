#!/usr/bin/env python3
"""
build.py - top-level build script for Stride2D.

  python3 build.py deps                 clone ../box2d (crustos/box2d) and ../CCSharp (+ its crust and coost) beside this repo
  python3 build.py native [--avx2]      build Box2D-Packed + the pb2_* shim into build/box2d (static + shared)
  python3 build.py ccsharp              build the CCSharp translator (needs the .NET SDK, no NuGet)
  python3 build.py dotnet GAME          run a game on .NET: the reference build
  python3 build.py check GAME           does GAME translate to C? (prints what is outside the C# subset)
  python3 build.py player GAME [--verify] [--static] [--run]    translate, build native, optionally compare with .NET
  python3 build.py bench [--avx2] [--cachegrind]   native physics benchmark (pyramid + circles); prints a state hash that must not change
  python3 build.py status | clean

GAME is a folder under samples/ (or any folder of .cs files with a static Main).
"""
import argparse, os, shutil, subprocess, sys

ROOT = os.path.dirname(os.path.abspath(__file__))
PARENT = os.path.dirname(ROOT)
BUILD = os.path.join(ROOT, "build")
REPOS = {"box2d": "https://github.com/crustos/box2d", "CCSharp": "https://github.com/crustos/CCSharp"}
TOOL = os.path.join(ROOT, "tools", "player_build.py")


def log(m): print("\033[1;36m[build.py]\033[0m " + m, flush=True)
def die(m): print("\033[1;31m[build.py] ERROR:\033[0m " + m, file=sys.stderr); sys.exit(1)


def run(cmd, cwd=ROOT):
    log("$ " + " ".join(cmd))
    rc = subprocess.run(cmd, cwd=cwd).returncode
    if rc: sys.exit(rc)


def clone(name):
    p = os.path.join(PARENT, name)
    if os.path.isdir(p): log("%s: found at %s" % (name, p)); return
    if not shutil.which("git"): die("git not found")
    run(["git", "clone", "--depth", "1", REPOS[name], p])


def need(tool, hint):
    if not shutil.which(tool): die("`%s` not found. %s" % (tool, hint))


def cmd_deps(a):
    for n in REPOS: clone(n)
    ccs = os.path.join(PARENT, "CCSharp")
    if not os.path.isdir(os.path.join(PARENT, "crust")):   # CCSharp's own build.py clones crust + coost
        run([sys.executable, "build.py", "deps"], cwd=ccs)


def cmd_native(a):
    need("cmake", "Install cmake."); need("cc", "Install a C compiler.")
    b2 = os.path.join(PARENT, "box2d")
    if not os.path.isdir(b2): die("../box2d is missing: python3 build.py deps")
    run(["cmake", "-S", "src/native/box2d", "-B", "build/box2d", "-DCMAKE_BUILD_TYPE=Release",
         "-DSTRIDE2D_BOX2D_DIR=" + b2, "-DSTRIDE2D_AVX2=" + ("ON" if a.avx2 else "OFF")])
    run(["cmake", "--build", "build/box2d", "-j", str(os.cpu_count() or 4), "--target", "stride2d_box2d_static", "stride2d_box2d"])


def cmd_ccsharp(a):
    need("dotnet", "Install the .NET SDK (8 or later).")
    run([sys.executable, "build.py", "compiler"], cwd=os.path.join(PARENT, "CCSharp"))


def game_args(a):
    if not os.path.isdir(a.game): die("no such game folder: " + a.game)
    return [a.game]


def cmd_dotnet(a):  need("dotnet", "Install the .NET SDK."); run([sys.executable, TOOL] + game_args(a) + ["--dotnet"])
def cmd_check(a):   run([sys.executable, TOOL] + game_args(a) + ["--check"])


def cmd_player(a):
    cmd = [sys.executable, TOOL] + game_args(a)
    cmd += [f for f, on in (("--verify", a.verify), ("--static", a.static), ("--run", a.run)) if on]
    run(cmd)


def cmd_bench(a):
    """Compiles bench/physics_bench.c against the built shim and runs it; --cachegrind profiles it (needs valgrind)."""
    if not os.path.exists(os.path.join(BUILD, "box2d", "libstride2d_box2d_static.a")): cmd_native(a)
    b = os.path.join(BUILD, "box2d"); exe = os.path.join(BUILD, "physics_bench")
    run(["cc", "-O2", "-g", "-ffp-contract=off", "-w", "-Isrc/native/box2d", "-o", exe, "bench/physics_bench.c",
         "-L" + b, "-L" + os.path.join(b, "box2d", "src"), "-lstride2d_box2d_static", "-lbox2d", "-lm", "-lpthread"])
    run([exe])
    if a.cachegrind:
        need("valgrind", "sudo apt install valgrind")
        out = os.path.join(BUILD, "cachegrind.out")
        run(["valgrind", "--tool=cachegrind", "--cache-sim=yes", "--branch-sim=yes", "--cachegrind-out-file=" + out, exe])
        run(["cg_annotate", out, "--show=Ir,D1mr,Bcm", "--sort=Ir", "--threshold=1"])


def cmd_status(a):
    for n in ("box2d", "CCSharp", "crust", "coost"):
        p = os.path.join(PARENT, n); log("%-8s %s" % (n, p if os.path.isdir(p) else "MISSING"))
    for t in ("python3", "git", "cmake", "cc", "dotnet"):
        log("%-8s %s" % (t, shutil.which(t) or "MISSING"))
    log("shim     %s" % ("built" if os.path.exists(os.path.join(BUILD, "box2d", "libstride2d_box2d_static.a")) else "not built (native)"))
    log("ccs.dll  %s" % ("built" if os.path.exists(os.path.join(PARENT, "CCSharp", "build", "compiler", "ccs.dll")) else "not built (ccsharp)"))


def cmd_clean(a): shutil.rmtree(BUILD, ignore_errors=True); log("removed build/")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", choices=["deps", "native", "ccsharp", "dotnet", "check", "player", "bench", "status", "clean"])
    ap.add_argument("game", nargs="?")
    ap.add_argument("--avx2", action="store_true"); ap.add_argument("--cachegrind", action="store_true")
    ap.add_argument("--verify", action="store_true"); ap.add_argument("--static", action="store_true"); ap.add_argument("--run", action="store_true")
    a = ap.parse_args()
    if a.command in ("dotnet", "check", "player") and not a.game: die("%s needs a GAME folder, e.g. samples/Headless2D" % a.command)
    globals()["cmd_" + a.command](a)


if __name__ == "__main__":
    main()

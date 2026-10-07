#!/usr/bin/env python3
"""
gfx_build.py - builds the Gfx2D renderer (src/native/gfx2d) as a static and a shared library, and the native test driver.

  python3 tools/gfx_build.py [--out DIR] [--cc CC] [--no-gl] [--no-x11] [--force]

Writes DIR/libgfx2d_static.a, DIR/libgfx2d.so and DIR/gfx_driver (default DIR: build/gfx). Files newer than their sources are not rebuilt.
The desktop OpenGL backend loads EGL/GLES/X11 with dlopen, so nothing but libdl and libm is linked; --no-gl leaves it out (CPU backend only).
"""
import argparse, os, shutil, subprocess, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "src", "native", "gfx2d")
CORE = ["gfx2d_core.c", "gfx2d_soft.c", "gfx2d_font.c", "gfx2d_font_data.c"]
FLAGS = ["-O2", "-g", "-ffp-contract=off", "-Wall", "-Wno-unused-function", "-fvisibility=default"]


def newer(out, deps):
    return not os.path.exists(out) or any(os.path.getmtime(d) > os.path.getmtime(out) for d in deps)


def sources(gl):
    s = list(CORE) + (["gfx2d_gl.c"] if gl else [])
    return [os.path.join(SRC, f) for f in s]


def headers():
    return [os.path.join(SRC, f) for f in os.listdir(SRC) if f.endswith(".h")]


def defines(gl, x11):
    d = ["-DGFX_HAVE_SOFT=1"]
    if gl: d.append("-DGFX_HAVE_GL=1")
    if not x11: d.append("-DGFX_NO_X11=1")
    return d


def build(out=None, cc=None, gl=True, x11=True, force=False, quiet=False):
    """Returns a dict with the paths of what was built: static, shared, driver."""
    cc = cc or os.environ.get("CC") or "cc"
    if not shutil.which(cc): raise SystemExit("gfx_build: `%s` not found" % cc)
    out = os.path.abspath(out or os.path.join(ROOT, "build", "gfx"))
    os.makedirs(out, exist_ok=True)
    srcs, hdrs, defs = sources(gl), headers(), defines(gl, x11)
    deps = srcs + hdrs
    res = {"static": os.path.join(out, "libgfx2d_static.a"), "shared": os.path.join(out, "libgfx2d.so"), "driver": os.path.join(out, "gfx_driver")}

    def sh(cmd):
        if not quiet: print("$ " + " ".join(cmd), flush=True)
        subprocess.run(cmd, check=True)

    objs = []
    for s in srcs:
        o = os.path.join(out, os.path.basename(s)[:-2] + ".o")
        if force or newer(o, [s] + hdrs): sh([cc, "-c", "-fPIC", "-std=gnu99"] + FLAGS + defs + ["-o", o, s])
        objs.append(o)
    if force or newer(res["static"], objs):
        if os.path.exists(res["static"]): os.remove(res["static"])
        sh(["ar", "rcs", res["static"]] + objs)
    if force or newer(res["shared"], objs): sh([cc, "-shared", "-o", res["shared"]] + objs + ["-ldl", "-lm"])
    test = os.path.join(SRC, "test")
    tsrc = [os.path.join(test, "driver.c"), os.path.join(test, "scene.c")]
    if force or newer(res["driver"], tsrc + [res["static"]] + hdrs):
        sh([cc, "-std=gnu99", "-O2", "-ffp-contract=off", "-o", res["driver"]] + tsrc + [res["static"], "-ldl", "-lm"])
    for name in ("input_test", "input_driver", "font_test", "clip_test"):
        exe = os.path.join(out, "gfx_" + name)
        tc = [os.path.join(test, "font_test.c" if name == "clip_test" else name + ".c")] + ([os.path.join(test, name[:4] + "_scene.c")] if name in ("font_test", "clip_test") else [])
        if force or newer(exe, tc + [res["static"]] + hdrs):
            sh([cc, "-std=gnu99", "-O2", "-ffp-contract=off", "-o", exe] + tc + [res["static"], "-ldl", "-lm"])
        res[name] = exe
    # X11 helper that sends input to the window (needs the X11 headers and library: left out where they are not)
    if x11 and gl and os.path.exists("/usr/include/X11/Xlib.h"):
        exe = os.path.join(out, "x11_input")
        if force or newer(exe, [os.path.join(test, "x11_input.c")]):
            r = subprocess.run([cc, "-o", exe, os.path.join(test, "x11_input.c"), "-lX11"], capture_output=True)
            if r.returncode == 0: res["x11_input"] = exe
        else: res["x11_input"] = exe
    # test helpers (LD_PRELOAD shim and window closer); they need only libdl / the X11 library at run time
    nodl = os.path.join(out, "nodl.so")
    if force or newer(nodl, [os.path.join(test, "nodl.c")]):
        sh([cc, "-shared", "-fPIC", "-o", nodl, os.path.join(test, "nodl.c"), "-ldl"])
    res["nodl"] = nodl
    return res


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out"); ap.add_argument("--cc"); ap.add_argument("--no-gl", action="store_true")
    ap.add_argument("--no-x11", action="store_true"); ap.add_argument("--force", action="store_true")
    a = ap.parse_args()
    r = build(a.out, a.cc, not a.no_gl, not a.no_x11, a.force)
    for k, v in r.items(): print("%-7s %s" % (k, v))


if __name__ == "__main__":
    main()

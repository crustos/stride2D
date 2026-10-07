#!/usr/bin/env python3
"""
gfx_test.py - checks the Gfx2D renderer: the CPU backend against itself and the stats, the GL backend against the CPU one, and (when a browser and a
WebAssembly toolchain are there) WebGL2 and WebGPU against the CPU one. A check whose tools are missing is reported as `skip`, never as `ok`.

  python3 tools/gfx_test.py [--web] [--keep]

Needs numpy and Pillow for the comparisons. --web adds the browser checks (clang + wasi-libc, node + playwright-core, Chromium; WebGPU also xvfb-run + lavapipe).
Exit code 1 if any check failed.
"""
import argparse, json, os, shutil, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import gfx_build

SRC = os.path.join(ROOT, "src", "native", "gfx2d")
results = []


def report(name, status, why=""):
    results.append((name, status))
    print("  %-34s %-5s %s" % (name, status, why), flush=True)


def drive(exe, work, env=None, args=("2",), preload=None, timeout=120):
    e = dict(os.environ, STRIDE2D_HEADLESS="1")
    e.update(env or {})
    if preload: e["LD_PRELOAD"] = preload
    r = subprocess.run([exe] + list(args), cwd=work, env=e, capture_output=True, text=True, timeout=timeout)
    hashes = [l.split()[3] for l in r.stdout.splitlines() if l.startswith("frame ")]
    info = next((l for l in r.stdout.splitlines() if l.startswith("backend=")), "")
    backend = int(info.split()[0].split("=")[1]) if info else -1
    stats = next((l.split()[4:] for l in r.stdout.splitlines() if l.startswith("frame ")), [])
    return r.returncode, backend, hashes, stats, r.stdout + r.stderr


def compare(a, b, mean_max, big_max):
    r = subprocess.run([sys.executable, os.path.join(HERE, "gfx_compare.py"), a, b, "--mean-max", str(mean_max), "--big-max", str(big_max)],
                       capture_output=True, text=True)
    return r.returncode == 0, (r.stdout + r.stderr).strip().replace("\n", " ")[:160]


# What a window must deliver for x11_input's fixed sequence (move, click, wheel up and down, a, Shift+A, Enter, Left, Escape): [type, a, b, c, d]
X11_EXPECT = [[1, 40, 30, 0, 0], [2, 40, 30, 0, 0], [3, 40, 30, 0, 0], [4, 40, 30, 0, 120], [4, 40, 30, 0, -120],
              [5, 65, 0, 0, 0], [7, 97, 0, 0, 0], [6, 65, 0, 0, 0], [5, 65, 0, 0, 1], [7, 65, 0, 0, 0], [6, 65, 0, 0, 1],
              [5, 257, 0, 0, 0], [6, 257, 0, 0, 0], [5, 263, 0, 0, 0], [6, 263, 0, 0, 0], [5, 256, 0, 0, 0]]
# and what a page must deliver for the same input from a browser (which also reports the Shift key itself, and the focus the click gives the canvas)
WEB_EXPECT = [[1, 40, 30, 0, 0], [8, 1, 0, 0, 0], [2, 40, 30, 0, 0], [3, 40, 30, 0, 0], [4, 40, 30, 0, 120],
              [5, 65, 0, 0, 0], [7, 97, 0, 0, 0], [6, 65, 0, 0, 0],
              [5, 340, 0, 0, 1], [5, 65, 0, 0, 1], [7, 65, 0, 0, 0], [6, 65, 0, 0, 1], [6, 340, 0, 0, 0],
              [5, 257, 0, 0, 0], [6, 257, 0, 0, 0], [5, 263, 0, 0, 0], [6, 263, 0, 0, 0], [5, 256, 0, 0, 0], [6, 256, 0, 0, 0]]


def native_input(work, libs):
    exe = libs["input_test"]
    for be in ("soft", "gl"):
        e = dict(os.environ, STRIDE2D_HEADLESS="1", STRIDE2D_GFX=be)
        r = subprocess.run([exe], cwd=work, env=e, capture_output=True, text=True)
        if r.returncode and "init failed" in r.stdout and be == "gl": report("input queue (gl)", "skip", "no GL here"); continue
        report("input queue (%s)" % be, "ok" if r.returncode == 0 and "input ok" in r.stdout else "FAIL", (r.stdout.strip().splitlines() or [""])[-1][:100])
    if "x11_input" not in libs or not shutil.which("xvfb-run"):
        return report("window input (X11)", "skip", "needs xvfb-run and the X11 headers")
    sh = "%s 8 > ev.txt & sleep 1.5; %s 5; wait" % (libs["input_driver"], libs["x11_input"])
    r = subprocess.run(["xvfb-run", "-a", "bash", "-c", sh], cwd=work, capture_output=True, text=True, timeout=60, env=dict(os.environ, STRIDE2D_GFX="gl"))
    txt = open(os.path.join(work, "ev.txt")).read() if os.path.exists(os.path.join(work, "ev.txt")) else ""
    if "windowed=1" not in txt: return report("window input (X11)", "skip", "no GL window under xvfb")
    got = [[int(v) for v in l.split()[1:]] for l in txt.splitlines() if l.startswith("ev ")]
    report("window input (X11)", "ok" if got == X11_EXPECT else "FAIL", "" if got == X11_EXPECT else "got %s" % got[:20])


def native_clip(work, libs):
    """The clip scene: soft is repeatable and cuts where it should (the hidden tile and the area outside every clip are empty); GL draws the same."""
    exe = libs["clip_test"]
    pics = {}
    for be in ("soft", "gl"):
        r = subprocess.run([exe], cwd=work, env=dict(os.environ, STRIDE2D_GFX=be), capture_output=True, text=True)
        if r.returncode:
            report("clip scene (%s)" % be, "skip" if be == "gl" else "FAIL", "no GL here" if be == "gl" else r.stdout[-120:]); continue
        pics[be] = os.path.join(work, "clip_%s.ppm" % be)
        shutil.move(os.path.join(work, "frame_0000.ppm"), pics[be])
        if be == "soft":
            from PIL import Image
            im = Image.open(pics[be]).convert("RGB")
            bg = im.getpixel((2, 2))
            # tile at world (300, 40) is hidden (clip 0x0), the tile at (60, 100) is cut to rows 90-120, so the rows under that band must be the background
            hidden = [im.getpixel((x, y)) for x in range(266, 334, 4) for y in range(190, 226, 4)]
            outside = [im.getpixel((x, y)) for x in range(30, 90, 3) for y in range(126, 152, 2)]
            report("clip hides what it should", "ok" if all(p == bg for p in hidden) and all(p == bg for p in outside) else "FAIL")
            top = [im.getpixel((x, y)) for x in range(30, 90, 3) for y in range(60 - 8, 60 + 8, 3)]
            report("no clip at the frame's start", "ok" if any(p != bg for p in top) else "FAIL")
    if "gl" in pics:
        ok, msg = compare(pics["soft"], pics["gl"], 0.1, 0.1)
        report("clip scene gl vs soft", "ok" if ok else "FAIL", msg)
    return pics.get("soft")


def native_font(work, libs):
    """The font scene: the soft picture is repeatable, has text where text should be, and GL draws the same."""
    exe = libs["font_test"]
    pics = {}
    for be in ("soft", "gl"):
        r = subprocess.run([exe], cwd=work, env=dict(os.environ, STRIDE2D_GFX=be), capture_output=True, text=True)
        if r.returncode:
            report("font scene (%s)" % be, "skip" if be == "gl" else "FAIL", "no GL here" if be == "gl" else r.stdout[-120:]); continue
        pics[be] = os.path.join(work, "font_%s.ppm" % be)
        shutil.move(os.path.join(work, "frame_0000.ppm"), pics[be])
        if be == "soft":
            hs = [l for l in r.stdout.splitlines() if l.startswith("hash")]
            r2 = subprocess.run([exe], cwd=work, env=dict(os.environ, STRIDE2D_GFX=be), capture_output=True, text=True)
            hs2 = [l for l in r2.stdout.splitlines() if l.startswith("hash")]
            report("font scene is deterministic", "ok" if hs and hs == hs2 else "FAIL", "%s vs %s" % (hs, hs2))
            nums = [l for l in r.stdout.splitlines() if l.startswith("font ")]
            want = ["size 14", "size 20", "size 28", "size 40"]
            report("font metrics", "ok" if len(nums) == 4 and all(w in n for w, n in zip(want, nums)) and all("?-fallback 0" in n for n in nums) else "FAIL", str(nums)[:100])
            from PIL import Image
            im = Image.open(pics[be]).convert("L")
            band = im.crop((0, 8, 400, 28)).tobytes()   # the first line of text: bright pixels where the glyphs are, the background elsewhere
            lit = sum(1 for v in band if v > 200)
            report("font scene has text", "ok" if 300 < lit < 3000 else "FAIL", "%d bright pixels" % lit)
    if "gl" in pics:
        ok, msg = compare(pics["soft"], pics["gl"], 0.1, 0.1)
        report("font scene gl vs soft", "ok" if ok else "FAIL", msg)
    return pics.get("soft")


def native(work, libs):
    exe = libs["driver"]
    rc, be, h1, stats, out = drive(exe, work, {"STRIDE2D_GFX": "soft"})
    if rc or be != 1: return report("soft backend runs", "FAIL", out[-150:])
    report("soft backend runs", "ok")
    want = ["calls", "6", "sprites", "9", "vertices", "21", "bytes", "924"]
    report("stats 6/9/21/924", "ok" if stats[:8] == want else "FAIL", " ".join(stats))
    rc, be, h2, _, _ = drive(exe, work, {"STRIDE2D_GFX": "soft"})
    report("soft is deterministic", "ok" if h1 == h2 and len(h1) == 2 else "FAIL", "%s vs %s" % (h1, h2))
    soft = os.path.join(work, "soft.ppm")
    shutil.move(os.path.join(work, "frame_0001.ppm"), soft)

    rc, be, hg, _, out = drive(exe, work, {"STRIDE2D_GFX": "gl"})
    if rc or be != 2:
        report("gl vs soft", "skip", "no usable EGL/GLES here (backend=%d)" % be)
    else:
        ok, msg = compare(soft, os.path.join(work, "frame_0001.ppm"), 0.1, 0.1)
        report("gl vs soft", "ok" if ok else "FAIL", msg)
        rc2, _, hg2, _, _ = drive(exe, work, {"STRIDE2D_GFX": "gl"})
        report("gl repeatable", "ok" if hg == hg2 else "FAIL")
    # no EGL/GLES/X11 at all: must fall back to the CPU picture, not refuse to start
    rc, be, hn, _, out = drive(exe, work, {}, preload=libs["nodl"])
    report("falls back without GL libs", "ok" if rc == 0 and be == 1 and hn == h1 else "FAIL", "backend=%d" % be)
    rc, be, _, _, out = drive(exe, work, {"STRIDE2D_GFX": "gl"}, preload=libs["nodl"])
    report("forced gl fails cleanly", "ok" if rc != 0 and "Segmentation" not in out else "FAIL", "rc=%d" % rc)
    return soft


def web(work, soft, keep, fsoft=None, csoft=None):
    need = {t: shutil.which(t) for t in ("clang", "node")}
    if not all(need.values()):
        return report("web (wasm build)", "skip", "needs clang and node")
    page = os.path.join(work, "page")
    os.makedirs(page)
    wasm = os.path.join(page, "stride2d-player.wasm")
    srcs = [os.path.join(SRC, f) for f in ("gfx2d_core.c", "gfx2d_web.c")] + [os.path.join(SRC, "test", f) for f in ("scene.c", "web_entry.c")]
    r = subprocess.run(["clang", "--target=wasm32-wasi", "-mexec-model=reactor", "-O2", "-ffp-contract=off", "-DGFX_HAVE_WEB=1", "-fuse-ld=lld", "-o", wasm] + srcs +
                       ["-Wl,--allow-undefined"], capture_output=True, text=True)
    if r.returncode:
        return report("web (wasm build)", "skip", "wasm toolchain missing: " + r.stderr.strip().splitlines()[-1][:110] if r.stderr.strip() else "")
    report("web (wasm build)", "ok")
    for f in ("index.html", "stride2d_web.js"): shutil.copy(os.path.join(SRC, "web", f), page)
    for api in ("webgl2", "webgpu"):
        cmd = ["node", os.path.join(HERE, "gfx_web_test.mjs"), "--dir", page, "--gfx", api, "--frames", "2", "--out", os.path.join(work, api + ".ppm")]
        if api == "webgpu":
            if not shutil.which("xvfb-run") and not os.environ.get("DISPLAY"): report(api + " vs soft", "skip", "needs xvfb-run"); continue
            if not os.environ.get("DISPLAY"): cmd = ["xvfb-run", "-a"] + cmd
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=240)
        line = (r.stdout.strip().splitlines() or [""])[-1]
        if r.returncode in (3, 4): report(api + " vs soft", "skip", line[:120] or r.stderr[-120:]); continue
        if r.returncode: report(api + " vs soft", "FAIL", line[:150]); continue
        ok, msg = compare(soft, os.path.join(work, api + ".ppm"), 0.5, 0.5)
        report(api + " vs soft", "ok" if ok else "FAIL", msg)
        cmd = [c for c in cmd if c != "--out" and not c.endswith(api + ".ppm")] + ["--input"]
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=240)
        try:
            res = json.loads((r.stdout.strip().splitlines() or ["{}"])[-1])
        except ValueError:
            res = {}
        got = res.get("events")
        report(api + " input", "ok" if got == WEB_EXPECT else "FAIL", "" if got == WEB_EXPECT else "got %s" % (got if got is not None else r.stdout[-150:]))
    for name, ref, scene_files in (("font", fsoft, ("font_scene.c",)), ("clip", csoft, ("clip_scene.c",))):
        if ref: web_scene(work, name, ref, scene_files)


def web_scene(work, name, ref, scene_files):
    fpage = os.path.join(work, name + "_page")
    os.makedirs(fpage)
    fsrcs = [os.path.join(SRC, f) for f in ("gfx2d_core.c", "gfx2d_web.c", "gfx2d_font.c", "gfx2d_font_data.c")] + [os.path.join(SRC, "test", f) for f in scene_files + ("web_entry.c",)]
    r = subprocess.run(["clang", "--target=wasm32-wasi", "-mexec-model=reactor", "-O2", "-ffp-contract=off", "-DGFX_HAVE_WEB=1", "-fuse-ld=lld", "-o",
                        os.path.join(fpage, "stride2d-player.wasm")] + fsrcs + ["-Wl,--allow-undefined"], capture_output=True, text=True)
    if r.returncode: return report(name + " scene (wasm build)", "FAIL", r.stderr.strip()[-150:])
    for f in ("index.html", "stride2d_web.js"): shutil.copy(os.path.join(SRC, "web", f), fpage)
    for api in ("webgl2", "webgpu"):
        cmd = ["node", os.path.join(HERE, "gfx_web_test.mjs"), "--dir", fpage, "--gfx", api, "--frames", "2", "--out", os.path.join(work, name + "_" + api + ".ppm")]
        if api == "webgpu":
            if not shutil.which("xvfb-run") and not os.environ.get("DISPLAY"): continue
            if not os.environ.get("DISPLAY"): cmd = ["xvfb-run", "-a"] + cmd
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=240)
        line = (r.stdout.strip().splitlines() or [""])[-1]
        if r.returncode in (3, 4): report("%s scene %s" % (name, api), "skip", line[:120]); continue
        if r.returncode: report("%s scene %s" % (name, api), "FAIL", line[:150]); continue
        ok, msg = compare(ref, os.path.join(work, name + "_" + api + ".ppm"), 0.5, 0.5)
        report("%s scene %s vs soft" % (name, api), "ok" if ok else "FAIL", msg)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--web", action="store_true"); ap.add_argument("--keep", action="store_true")
    a = ap.parse_args()
    try:
        import numpy, PIL  # noqa
    except ImportError:
        sys.exit("gfx_test: needs numpy and Pillow (pip install numpy pillow)")
    libs = gfx_build.build(quiet=True)
    work = tempfile.mkdtemp(prefix="gfx_test_")
    try:
        native_input(work, libs)
        soft = native(work, libs)
        fsoft = native_font(work, libs)
        csoft = native_clip(work, libs)
        if a.web and soft: web(work, soft, a.keep, fsoft, csoft)
    finally:
        if a.keep: print("kept " + work)
        else: shutil.rmtree(work, ignore_errors=True)
    bad = [n for n, s in results if s == "FAIL"]
    print("\n%d ok, %d skipped, %d failed" % (sum(s == "ok" for _, s in results), sum(s == "skip" for _, s in results), len(bad)))
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()

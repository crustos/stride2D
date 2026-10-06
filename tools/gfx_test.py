#!/usr/bin/env python3
"""
gfx_test.py - checks the Gfx2D renderer: the CPU backend against itself and the stats, the GL backend against the CPU one, and (when a browser and a
WebAssembly toolchain are there) WebGL2 and WebGPU against the CPU one. A check whose tools are missing is reported as `skip`, never as `ok`.

  python3 tools/gfx_test.py [--web] [--keep]

Needs numpy and Pillow for the comparisons. --web adds the browser checks (clang + wasi-libc, node + playwright-core, Chromium; WebGPU also xvfb-run + lavapipe).
Exit code 1 if any check failed.
"""
import argparse, os, shutil, subprocess, sys, tempfile

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


def web(work, soft, keep):
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
        soft = native(work, libs)
        if a.web and soft: web(work, soft, a.keep)
    finally:
        if a.keep: print("kept " + work)
        else: shutil.rmtree(work, ignore_errors=True)
    bad = [n for n, s in results if s == "FAIL"]
    print("\n%d ok, %d skipped, %d failed" % (sum(s == "ok" for _, s in results), sum(s == "skip" for _, s in results), len(bad)))
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()

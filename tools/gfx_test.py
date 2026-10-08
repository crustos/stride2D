#!/usr/bin/env python3
"""
gfx_test.py - checks the Gfx2D renderer: the CPU backend against itself and the stats, the GL backend against the CPU one, and (when a browser and a
WebAssembly toolchain are there) WebGL2 and WebGPU against the CPU one. A check whose tools are missing is reported as `skip`, never as `ok`.

  python3 tools/gfx_test.py [--web] [--keep]

Needs numpy and Pillow for the comparisons. --web adds the browser checks (clang + wasi-libc, node + playwright-core, Chromium; WebGPU also xvfb-run + lavapipe).
Exit code 1 if any check failed.
"""
import argparse, json, math, os, shutil, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import gfx_build
import gfx_fx_gen

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


def _bc(c, brightness, contrast):
    k = 1 + contrast if contrast < 0 else 1 + 3 * contrast
    return [(x - 0.5) * k + 0.5 + brightness for x in c]


def _tint(c, col, amount):
    return [x * (1 - amount) + x * col[i] * amount for i, x in enumerate(c)]


def fx_expected(ppm):
    """What the effect scene (test/fx_scene.c) must hold, computed from the formulas in fx/*.fx and the numbers in the scene, not from any backend: each
    sampled pixel is within one level of it (the picture is 8 bits, the formulas are not). Returns (ok, message)."""
    from PIL import Image
    im = Image.open(ppm).convert("RGB")
    bg = im.getpixel((390, 5))                       # the background, where no effect reaches (the right part is clipped to rows 40..140)
    cl = lambda v: min(255.0, max(0.0, v))
    def want(c, f):                                  # c: bytes -> the effect's result in 0..255
        return [cl(v * 255) for v in f([x / 255 for x in c])]
    bad, n = [], 0
    def expect(name, xy, exp):
        nonlocal n
        n += 1
        got = im.getpixel(xy)
        if any(abs(g - e) > 1.0 for g, e in zip(got, exp)):
            bad.append("%s at %s: got %s want %s" % (name, xy, got, [round(e, 1) for e in exp]))
    rows = (("upper", 60, lambda i: (17 * i, 128, 17 * (15 - i))), ("lower", 190, lambda i: (17 * i, 17 * i, 17 * i)))
    for i in range(16):
        x = 25 * i + 12
        for band, y, raw in rows:
            c = raw(i)
            if i < 4:
                f = lambda v: _bc(v, 0.1, 0.15)
            elif i < 8:
                f = lambda v: _tint(v, (1.0, 0.5, 0.1), 0.6)
            elif i < 12:
                f = lambda v: _tint(_bc(v, -0.3, -0.5), (0.2, 0.4, 1.0), 0.5)
            elif i < 14:                             # NaN brightness -> the default 0; clipped to rows 40..140
                f = (lambda v: _bc(v, 0.0, -0.4)) if band == "upper" else None
            else:                                    # tint with every parameter defaulted; clipped to rows 40..140
                f = (lambda v: _tint(v, (1.0, 0.5, 0.1), 0.5)) if band == "upper" else None
            expect("bar %d %s" % (i, band), (x, y), want(c, f) if f else list(c))   # the lower band of the right part is outside its clip: untouched
    expect("background under effect A", (2, 2), want(bg, lambda v: _bc(v, 0.1, 0.15)))
    expect("background outside every clip", (390, 5), list(bg))
    expect("clipped tint, rows inside", (362, 135), want((17 * 14, 17 * 14, 17 * 14), lambda v: _tint(v, (1.0, 0.5, 0.1), 0.5)))
    expect("clipped bc, rows inside", (312, 135), want((17 * 12, 17 * 12, 17 * 12), lambda v: _bc(v, 0.0, -0.4)))
    expect("clipped bc, rows just outside", (312, 145), [17 * 12] * 3)
    expect("disc after the effects", (200, 120), [255, 255, 255])
    return not bad, ("%d pixels as computed" % n) if not bad else "; ".join(bad[:3])


def _bg(x, y):
    """The bytes of the bars of the second effect scene (test/fx2_scene.c) at pixel x, y: upper half (i/15, .5, 1-i/15), lower half grey i/15."""
    i = x // 25
    return (17 * i, 128, 17 * (15 - i)) if y < 120 else (17 * i,) * 3


def _ot_blend_ch(m, d, u):
    """One channel of an OpenToonz blend mode (igs_color_blend.cpp), the picture opaque: d the picture, u the color."""
    clamp = lambda v: min(1.0, max(0.0, v))
    screen = lambda a, b: 1.0 - (1.0 - a) * (1.0 - b)
    burn = lambda a, b: 0.0 if b <= 0 else 1.0 - min(1.0, (1.0 - a) / b)
    dodge = lambda a, b: 1.0 if b >= 1 else min(1.0, a / (1.0 - b))
    if m == 0: return u
    if m == 1: return d * u
    if m == 2: return 1.0 if u <= 0 else d / u
    if m == 3: return burn(d, u)
    if m == 4: return clamp(d + u - 1.0)
    if m == 5: return min(d, u)
    if m == 7: return max(d, u)
    if m == 8: return screen(d, u)
    if m == 9: return dodge(d, u)
    if m == 10: return min(1.0, d + u)
    if m == 12: return u * 2.0 * d if d < 0.5 else screen(u, 2.0 * d - 1.0)
    if m == 13:
        if u < 0.5: return d + (d - d * d) * (2 * u - 1)
        if d < 0.25: return d + (2 * u - 1) * (((16 * d - 12) * d + 4) * d - d)
        return d + (2 * u - 1) * (math.sqrt(d) - d)
    if m == 14: return d * 2.0 * u if u < 0.5 else screen(d, 2.0 * u - 1.0)
    if m == 15: return burn(d, 2.0 * u) if u < 0.5 else dodge(d, 2.0 * u - 1.0)
    if m == 16: return clamp(d + 2.0 * u - 1.0) if u < 0.5 else min(1.0, d + 2.0 * u - 1.0)
    if m == 17: return min(2.0 * u, d) if u < 0.5 else max(2.0 * u - 1.0, d)
    return 0.0 if (burn(d, 2.0 * u) if u < 0.5 else dodge(d, 2.0 * u - 1.0)) < 0.5 else 1.0


def _ot_blend(m, rgb, col, a, op):
    lum = lambda c: 0.298912 * c[0] + 0.586611 * c[1] + 0.114478 * c[2]
    if m == 6: b = col if not lum(rgb) < lum(col) else rgb      # darker color: the color wins unless the picture is darker
    elif m == 11: b = col if lum(rgb) < lum(col) else rgb
    else: b = [_ot_blend_ch(m, d, u) for d, u in zip(rgb, col)]
    return [d + (x - d) * a * op for d, x in zip(rgb, b)]


def _wrap(h, lo, hi):
    return h - (hi - lo) * math.floor((h - lo) / (hi - lo))


def _hue_adj(h, pivot, scale, shift):
    if scale == 1 and shift == 0:
        return h
    return _wrap(_wrap(h - pivot, -180, 180) * scale + pivot + shift, 0, 360)


def _hsv_adjust(rgb, p):
    import colorsys
    h, s, v = colorsys.rgb_to_hsv(*rgb)
    h *= 360
    h = _hue_adj(h, p["hp"], p["hs"], p["hh"])
    if p["sc"] != 1 or p["sh"] != 0: s = max(0.0, (s - p["sp"]) * p["sc"] + p["sp"] + p["sh"])
    if p["vc"] != 1 or p["vh"] != 0: v = (v - p["vp"]) * p["vc"] + p["vp"] + p["vh"]
    return list(colorsys.hsv_to_rgb(h / 360, s, v))


def _hls_adjust(rgb, p, cyl):
    import colorsys
    h, l, s = colorsys.rgb_to_hls(*rgb)
    h *= 360
    if not cyl: s = max(rgb) - min(rgb)
    h = _hue_adj(h, p["hp"], p["hs"], p["hh"])
    if p["lc"] != 1 or p["lh"] != 0: l = (l - p["lp"]) * p["lc"] + p["lp"] + p["lh"]
    if p["sc"] != 1 or p["sh"] != 0: s = (s - p["sp"]) * p["sc"] + p["sp"] + p["sh"]
    if s == 0: return [l] * 3
    if cyl:
        m2 = l * (1 + s) if l <= 0.5 else l + s - l * s
        m1 = 2 * l - m2
    else:
        m2, m1 = l + s * 0.5, l - s * 0.5
    def calc(hue):
        hh = hue % 360
        if hh < 60: return m1 + (m2 - m1) * hh / 60
        if hh < 180: return m2
        if hh < 240: return m1 + (m2 - m1) * (240 - hh) / 60
        return m1
    return [calc(h + 120), calc(h), calc(h - 120)]


def _levels(v, lo, hi, g, olo, ohi, clamp=True):
    v = hi if hi == lo else (v - lo) / (hi - lo)
    v = min(1.0, max(0.0, v)) if clamp or abs(ohi - 1) > 1e-6 else max(0.0, v)
    if g != 1 and g != 0:
        if 0 < v < 1: v = v ** (1 / g)
        elif v > 1: v = 1 + (v - 1) / g
    v = olo + v * (ohi - olo)
    return min(1.0, max(0.0, v)) if clamp else max(0.0, v)


def _curve(ty, t):
    return (t, t * t, 1 - (1 - t) ** 2)[ty - 1] if ty else (-2 * t + 3) * t * t


def _over(rgb, c1, c2, f, op):
    pm = [c1[i] * c1[3] * (1 - f) + c2[i] * c2[3] * f for i in range(3)]
    a = c1[3] * (1 - f) + c2[3] * f
    return [pm[i] * op + rgb[i] * (1 - a * op) for i in range(3)]


def fx2_expected(ppm):
    """What the second effect scene (test/fx2_scene.c) must hold, from OpenToonz's formulas written out again here (not from any backend and not from the fx files).
    Twelve pixels in each of the sixteen cells, each within 1.5 levels. The wave cell is only compared with the CPU picture. Returns (ok, message)."""
    from PIL import Image
    im = Image.open(ppm).convert("RGB")
    bad, n = [], 0
    black, white = (0, 0, 0, 1), (1, 1, 1, 1)
    def cellfx(c, r):
        x0, y0 = 100 * c, 60 * r
        cx, cy = x0 + 50, y0 + 30
        if (c, r) == (0, 0): return lambda rgb, px, py: _ot_blend(1, rgb, (1, .5, .1), 1, 1)
        if (c, r) == (1, 0): return lambda rgb, px, py: _ot_blend(12, rgb, (.3, .6, .9), .8, .75)
        if (c, r) == (2, 0): return lambda rgb, px, py: _ot_blend(13, rgb, (.7, .4, .2), 1, 1)
        if (c, r) == (3, 0): return lambda rgb, px, py: _ot_blend(6, rgb, (.5, .5, .5), 1, 1)
        base = dict(hp=0, hs=1, hh=0, sp=0, sc=1, sh=0, vp=0, vc=1, vh=0, lp=0, lc=1, lh=0)
        if (c, r) == (0, 1): return lambda rgb, px, py: _hsv_adjust(rgb, dict(base, hh=40, vh=-0.1, sc=1.5))
        if (c, r) == (1, 1): return lambda rgb, px, py: _hls_adjust(rgb, dict(base, hh=-60, lc=0.8, sc=1.3), True)
        if (c, r) == (2, 1): return lambda rgb, px, py: _hls_adjust(rgb, dict(base, hp=120, hs=0.5, lh=0.1), False)
        if (c, r) == (3, 1): return lambda rgb, px, py: [_levels(v, .1, .9, 1.8, .05, .95) for v in rgb]
        if (c, r) == (0, 2):
            return lambda rgb, px, py: [_levels(rgb[0], .2, .8, 1, 0, 1), _levels(rgb[1], 0, 1, 2.2, 0, 1), _levels(rgb[2], 0, 1, 1, .1, .6)]
        if (c, r) == (1, 2):
            def lin(rgb, px, py):
                a = math.radians(30)
                dx, dy = px - cx, cy - py
                rad = dx * math.cos(a) + dy * math.sin(a)
                mr = 60.0
                t = 1.0
                if abs(rad) < mr:
                    t = (rad + mr) / 120.0
                    t -= math.floor(t)
                elif rad < 0: t = 0.0
                return _over(rgb, black, white, _curve(0, t), 1)
            return lin
        if (c, r) == (2, 2):
            def rad(rgb, px, py):
                d = math.hypot(px - cx, cy - py)
                t = d / 45 if d < 45 else 1.0
                inner = 10 / 45
                t = 0.0 if t <= inner else (t - inner) / (1 - inner)
                return _over(rgb, white, (0, 0, .5, .5), _curve(2, t), 1)
            return rad
        if (c, r) == (3, 2):
            return lambda rgb, px, py: _over(rgb, white, black, min(1.0, (abs(px - cx) + abs(cy - py)) / 60), 1)
        if (c, r) == (0, 3):
            return lambda rgb, px, py: _over(rgb, white, black, min(1.0, abs(px - cx) / 30 * abs(cy - py) / 30), 1)
        if (c, r) == (1, 3):
            def spin(rgb, px, py):
                sa, ea = math.radians(45), math.radians(270)
                p = math.atan2(cy - py, px - cx) - sa
                if p < 0: p += 2 * math.pi
                rg = ea - sa
                t = p / rg if rg >= p else (1.0 if math.pi + rg / 2 > p else 0.0)
                return _over(rgb, black, white, t, 1)
            return spin
        if (c, r) == (2, 3):
            pts = [(290, 190, (1, 0, 0, 1)), (210, 190, (0, 1, 0, 1)), (210, 230, (0, 0, 1, 1)), (290, 230, (1, 1, 0, 1))]
            def four(rgb, px, py):
                w = [1 / max(math.hypot(px - x, py - y), 0.001) for x, y, _ in pts]
                pm = [sum(wi * col[i] * col[3] for wi, (_, _, col) in zip(w, pts)) / sum(w) for i in range(3)]
                return [pm[i] + rgb[i] * (1 - sum(wi * col[3] for wi, (_, _, col) in zip(w, pts)) / sum(w)) for i in range(3)]
            return four
        return None                                  # the wave
    for r in range(4):
        for c in range(4):
            f = cellfx(c, r)
            if f is None:
                continue
            for dy in (10, 30, 50):
                for dx in (12, 37, 62, 87):
                    x, y = 100 * c + dx, 60 * r + dy
                    bg = _bg(x, y)
                    exp = [min(255.0, max(0.0, v * 255)) for v in f([b / 255 for b in bg], x + 0.5, y + 0.5)]
                    got = im.getpixel((x, y))
                    n += 1
                    if any(abs(g - e) > 1.5 for g, e in zip(got, exp)):
                        bad.append("cell %d,%d at %s: got %s want %s" % (c, r, (x, y), got, [round(e, 1) for e in exp]))
    return not bad, ("%d pixels as computed" % n) if not bad else "%d wrong: " % len(bad) + "; ".join(bad[:3])


def fx3_expected(ppm):
    """What the light scene (test/fx3_scene.c) must hold: each lit pixel from the light formulas written out again here. Twelve pixels per 100 x 60 block, within 1.5 levels."""
    from PIL import Image
    im = Image.open(ppm).convert("RGB")
    W, H = 400.0, 240.0
    smooth = lambda t: t * t * (3 - 2 * t)
    def att(d, r, curve):
        t = min(1.0, max(0.0, 1 - d / r))
        return t if curve == 0 else smooth(t) if curve == 1 else t * t
    def point(px, py, x, y, r, k, col, curve):
        if k <= 0 or r <= 0: return [0, 0, 0]
        a = att(math.hypot(px - x * W, py - y * H) / H, r, curve)
        return [c * k * a for c in col]
    def lit(rgb, amb, l, glow):
        return [rgb[i] * (amb[i] + l[i]) + l[i] * glow for i in range(3)]
    def left(rgb, px, py):
        ls = [point(px, py, .25, .35, .3, 1.2, (1, .8, .5), 1), point(px, py, .15, .75, .25, 1.0, (.4, .7, 1), 1), point(px, py, .4, .6, .2, .8, (1, .4, .6), 1)]
        return lit(rgb, (.2, .25, .4), [sum(v[i] for v in ls) for i in range(3)], 0.2)
    def top_right(rgb, px, py):
        return lit(rgb, (.1, .1, .1), point(px, py, .75, .25, .3, 1.0, (1, 1, 1), 0), 0.0)
    def spot(rgb, px, py):
        ex, ey = px - .75 * W, .5 * H - py
        dist = math.hypot(ex, ey)
        cosang = (ex * math.cos(math.radians(-90)) + ey * math.sin(math.radians(-90))) / dist if dist > 0 else 1.0
        c0, c1 = math.cos(math.radians(30)), math.cos(math.radians(30 * 0.6))
        f = smooth(min(1.0, max(0.0, (cosang - c0) / max(c1 - c0, 1e-4))))
        l = [c * 1.5 * att(dist / H, 0.45, 2) * f for c in (1, .95, .8)]
        return lit(rgb, (.1, .1, .15), l, 0.1)
    bad, n = [], 0
    for r in range(4):
        for c in range(4):
            fn = left if c < 2 else (top_right if r < 2 else spot)
            for dy in (10, 30, 50):
                for dx in (12, 37, 62, 87):
                    x, y = 100 * c + dx, 60 * r + dy
                    exp = [min(255.0, max(0.0, v * 255)) for v in fn([b / 255 for b in _bg(x, y)], x + 0.5, y + 0.5)]
                    got = im.getpixel((x, y))
                    n += 1
                    if any(abs(g - e) > 1.5 for g, e in zip(got, exp)):
                        bad.append("%s at %s: got %s want %s" % (fn.__name__, (x, y), got, [round(e, 1) for e in exp]))
    return not bad, ("%d pixels as computed" % n) if not bad else "%d wrong: " % len(bad) + "; ".join(bad[:3])


def fx4_expected(ppm):
    """What the scene_lights scene (test/fx4_scene.c) must hold: the lit bars from the formulas written out again here; a 16 x 12 grid of pixels, within 1.5 levels."""
    from PIL import Image
    im = Image.open(ppm).convert("RGB")
    W, H = 400.0, 240.0
    amb, glow, expo, mix_ = (0.1, 0.22, 0.15), 0.1, 1.3, 0.85
    lights = [(0.2, 0.3, 0.4, 1.0, (1, .85, .6), 0, 30, .4, 0), (0.45, 0.75, 0.35, 1.5, (.4, .7, 1), 0, 30, .4, 0), (0.55, 0.3, 0.7, 1.2, (1, 1, .9), 0, 25, .5, 1),
              (0.95, 0.9, 0.8, 1.0, (1, .6, .9), 140, 40, .8, 1), (0.8, 0.5, 0.5, 0.0, (1, 1, 1), 0, 30, .4, 0)]
    smooth = lambda t: t * t * (3 - 2 * t)
    def one(px, py, x, y, r, k, col, ang, cone, soft, kind):
        if k <= 0 or r <= 0: return [0, 0, 0]
        ex, ey = px - x * W, y * H - py
        dist = math.hypot(ex, ey)
        t = min(1.0, max(0.0, 1 - dist / H / r)) ** 2                  # quadratic falloff
        if kind:
            cosang = (ex * math.cos(math.radians(ang)) + ey * math.sin(math.radians(ang))) / dist if dist > 0 else 1.0
            c0, c1 = math.cos(math.radians(cone)), math.cos(math.radians(cone * (1 - soft)))
            t *= smooth(min(1.0, max(0.0, (cosang - c0) / max(c1 - c0, 1e-4))))
        return [c * k * t for c in col]
    bad, n = [], 0
    for gy in range(12):
        for gx in range(16):
            x, y = 25 * gx + 12, 20 * gy + 10
            rgb = [b / 255 for b in _bg(x, y)]
            ls = [one(x + 0.5, y + 0.5, *l[:4], l[4], *l[5:]) for l in lights]
            l = [expo * sum(v[i] for v in ls) for i in range(3)]
            exp = [min(255.0, max(0.0, (rgb[i] + (rgb[i] * (amb[i] + l[i]) + l[i] * glow - rgb[i]) * mix_) * 255)) for i in range(3)]
            got = im.getpixel((x, y))
            n += 1
            if any(abs(g - e) > 1.5 for g, e in zip(got, exp)):
                bad.append("at %s: got %s want %s" % ((x, y), got, [round(e, 1) for e in exp]))
    return not bad, ("%d pixels as computed" % n) if not bad else "%d wrong: " % len(bad) + "; ".join(bad[:3])


def native_fx(work, libs, key="fx_test", tag="fx", expect=None):
    """The effect scene: the soft picture is what the formulas say, repeatable and with every API answer right; GL draws the same."""
    exe = libs[key]
    expect = expect or fx_expected
    pics = {}
    for be in ("soft", "gl"):
        r = subprocess.run([exe], cwd=work, env=dict(os.environ, STRIDE2D_GFX=be), capture_output=True, text=True)
        if r.returncode:
            report("%s scene (%s)" % (tag, be), "skip" if be == "gl" else "FAIL", "no GL here" if be == "gl" else r.stdout[-120:]); continue
        pics[be] = os.path.join(work, "%s_%s.ppm" % (tag, be))
        shutil.move(os.path.join(work, "frame_0000.ppm"), pics[be])
        api = [l for l in r.stdout.splitlines() if l.startswith("api failures")]
        report("%s API answers (%s)" % (tag, be), "ok" if api == ["api failures 0"] else "FAIL", str(api))
        ok, msg = expect(pics[be])
        report("%s as computed (%s)" % (tag, be), "ok" if ok else "FAIL", msg)
        if be == "soft":
            hs = [l for l in r.stdout.splitlines() if l.startswith("hash")]
            r2 = subprocess.run([exe], cwd=work, env=dict(os.environ, STRIDE2D_GFX=be), capture_output=True, text=True)
            hs2 = [l for l in r2.stdout.splitlines() if l.startswith("hash")]
            report("%s scene is deterministic" % tag, "ok" if hs and hs == hs2 else "FAIL", "%s vs %s" % (hs, hs2))
    if "gl" in pics:
        ok, msg = compare(pics["soft"], pics["gl"], 0.1, 0.1)
        report("%s scene gl vs soft" % tag, "ok" if ok else "FAIL", msg)
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


def web(work, soft, keep, fsoft=None, csoft=None, xsoft=None, x2soft=None, x3soft=None, x4soft=None):
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
    for name, ref, scene_files in (("font", fsoft, ("font_scene.c",)), ("clip", csoft, ("clip_scene.c",)), ("fx", xsoft, ("fx_scene.c",)), ("fx2", x2soft, ("fx2_scene.c",)), ("fx3", x3soft, ("fx3_scene.c",)), ("fx4", x4soft, ("fx4_scene.c",))):
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
        if name in ("fx", "fx2", "fx3", "fx4"):       # and against the formulas themselves, not only against the CPU picture
            ok, msg = {"fx": fx_expected, "fx2": fx2_expected, "fx3": fx3_expected, "fx4": fx4_expected}[name](os.path.join(work, name + "_" + api + ".ppm"))
            report("%s as computed (%s)" % (name, api), "ok" if ok else "FAIL", msg)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--web", action="store_true"); ap.add_argument("--keep", action="store_true")
    a = ap.parse_args()
    try:
        import numpy, PIL  # noqa
    except ImportError:
        sys.exit("gfx_test: needs numpy and Pillow (pip install numpy pillow)")
    # before the build, which writes the generated files: is what is committed what the registry makes?
    try:
        stale = [os.path.relpath(p, ROOT) for p in gfx_fx_gen.generate(write=False)]
        report("effect registry is up to date", "ok" if not stale else "FAIL", ", ".join(stale) + (" (run tools/gfx_fx_gen.py)" if stale else ""))
    except gfx_fx_gen.FxError as e:
        report("effect registry is up to date", "FAIL", str(e))
    import contextlib, io
    with contextlib.redirect_stdout(io.StringIO()) as out:
        selftest_ok = gfx_fx_gen.selftest()
    report("effect registry self-test", "ok" if selftest_ok else "FAIL", "" if selftest_ok else out.getvalue().strip()[:150])
    libs = gfx_build.build(quiet=True)
    work = tempfile.mkdtemp(prefix="gfx_test_")
    try:
        native_input(work, libs)
        soft = native(work, libs)
        fsoft = native_font(work, libs)
        csoft = native_clip(work, libs)
        xsoft = native_fx(work, libs)
        x2soft = native_fx(work, libs, "fx2_test", "fx2", fx2_expected)
        x3soft = native_fx(work, libs, "fx3_test", "fx3", fx3_expected)
        x4soft = native_fx(work, libs, "fx4_test", "fx4", fx4_expected)
        if a.web and soft: web(work, soft, a.keep, fsoft, csoft, xsoft, x2soft, x3soft, x4soft)
    finally:
        if a.keep: print("kept " + work)
        else: shutil.rmtree(work, ignore_errors=True)
    bad = [n for n, s in results if s == "FAIL"]
    print("\n%d ok, %d skipped, %d failed" % (sum(s == "ok" for _, s in results), sum(s == "skip" for _, s in results), len(bad)))
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()

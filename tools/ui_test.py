#!/usr/bin/env python3
"""
ui_test.py - tests src/ui (the in-game UI) on Mono, against the C renderer and a Python oracle.

  python3 tools/ui_test.py

Needs mono-mcs and mono, numpy and Pillow, and the DejaVu font (fonts-dejavu-core). The .NET build of the repo does not compile src/ui (it needs the renderer's
generated bindings: see Stride2D.csproj), so these tests build the UI files, the generated GFX bindings (turned from [LibraryImport] into [DllImport], which
mcs understands) and tests/ui/*.cs with mcs, and run them against the real libgfx2d.so.
"""
import os, re, shutil, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import gfx_build, gen_pb2  # noqa

results = []


def report(name, status, why=""):
    results.append((name, status))
    print("  %-40s %-4s  %s" % (name, status, why))


def advances(size):
    """Oracle: the advance of each Latin-1 character as the baker measured it (font_bake.py: PIL's BASIC layout), '?' for the codes the font has no glyph for."""
    from PIL import ImageFont
    f = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", size, layout_engine=ImageFont.Layout.BASIC)
    return {c: float("%.4f" % f.getlength(chr(c))) for c in range(32, 256)}


def oracle_wrap(adv, text, max_w):
    """Independent of UIText.Wrap: split at new lines, then lay out the words greedily; a word wider than a whole line is cut where it overflows."""
    out = []
    for para in text.split("\n"):
        cur, w, started = "", 0.0, False
        for word in para.split(" "):
            ww = sum(adv.get(ord(c), adv[63]) for c in word)
            if max_w <= 0 or (started and w + adv[32] + ww <= max_w) or (not started and ww <= max_w):
                cur, w = (cur + " " + word, w + adv[32] + ww) if started else (word, ww)
                started = True
                continue
            if started: out.append(cur)
            cur, w = "", 0.0
            for ch in word:
                a = adv.get(ord(ch), adv[63])
                if w + a > max_w and cur != "":
                    out.append(cur)
                    cur, w = "", 0.0
                cur += ch
                w += a
            started = True
        out.append(cur)
    return out


CASES = [
    (0, 0, "Hello, World!"),
    (1, 120, "The quick brown fox jumps over the lazy dog"),
    (2, 200, "One two three four five six seven eight nine ten"),
    (3, 150, "Supercalifragilisticexpialidocious is long"),
    (0, 90, "line one\\nline two is a bit longer than one\\n\\nafter a blank line"),
    (1, 0, "no wrapping\\nbut new lines"),
    (0, 60, "a b c d e f g h i j k l m n o p"),
    (2, 400, "fits on one line"),
]


def main():
    try:
        import numpy, PIL  # noqa
    except ImportError:
        sys.exit("ui_test: needs numpy and Pillow")
    if not (shutil.which("mcs") and shutil.which("mono")):
        sys.exit("ui_test: needs mono-mcs and mono")
    libs = gfx_build.build(quiet=True)
    work = tempfile.mkdtemp(prefix="ui_test_")
    try:
        gen = os.path.join(work, "gen")
        gen_pb2.use("gfx2d")
        subprocess.run([sys.executable, os.path.join(HERE, "gen_pb2.py"), "--lib", "gfx2d", "generate", gen], check=True, capture_output=True)
        net = open(os.path.join(gen, "net", "GFX.net.cs")).read()
        net = re.sub(r"\[LibraryImport\(Lib, EntryPoint = (\"\w+\")\)\]( (?:public|private) static) partial", r"[DllImport(Lib, EntryPoint = \1)]\2 extern", net)
        open(os.path.join(work, "GFX.mono.cs"), "w").write(net)
        srcs = [os.path.join(ROOT, "src", "ui", "UIText.cs"), os.path.join(ROOT, "tests", "ui", "TextTest.cs"), os.path.join(work, "GFX.mono.cs")]
        exe = os.path.join(work, "TextTest.exe")
        r = subprocess.run(["mcs", "-sdk:4.5", "-unsafe", "-nowarn:0168,0219,0414,0649", "-out:" + exe] + srcs, capture_output=True, text=True)
        err = [l for l in (r.stdout + r.stderr).splitlines() if "error" in l]
        if r.returncode:
            return report("UI builds with mcs", "FAIL", "; ".join(err)[:300]) or sys.exit(1)
        report("UI builds with mcs", "ok")
        env = dict(os.environ, LD_LIBRARY_PATH=os.path.dirname(libs["shared"]), STRIDE2D_GFX="soft")

        # 1. the C# text layer draws the font scene exactly as the C test does
        c = subprocess.run([libs["font_test"]], cwd=work, env=env, capture_output=True, text=True)
        want = [l for l in c.stdout.splitlines() if l.startswith("hash")]
        shutil.move(os.path.join(work, "frame_0000.ppm"), os.path.join(work, "c.ppm"))
        m = subprocess.run(["mono", exe, "picture"], cwd=work, env=env, capture_output=True, text=True)
        got = [l for l in m.stdout.splitlines() if l.startswith("hash")]
        report("UIText.Draw == the C font scene", "ok" if want and want == got else "FAIL", "C %s, C# %s %s" % (want, got, m.stderr.strip()[-120:]))

        # 2. measure and wrap against the oracle
        with open(os.path.join(work, "cases.txt"), "w") as f:
            for font, w, text in CASES: f.write("%d\t%s\t%s\n" % (font, w, text))
        m = subprocess.run(["mono", exe, "cases", os.path.join(work, "cases.txt")], cwd=work, env=env, capture_output=True, text=True)
        lines = m.stdout.strip().splitlines()
        sizes = [14, 20, 28, 40]
        if len(lines) != len(CASES): return report("measure and wrap", "FAIL", "got %d lines: %s" % (len(lines), m.stdout[-200:] + m.stderr[-200:])) or sys.exit(1)
        bad = 0
        for (font, w, text), line in zip(CASES, lines):
            adv = advances(sizes[font])
            real = text.replace("\\n", "\n")
            width = sum(adv.get(ord(c), adv[63]) if ord(c) >= 32 else 0.0 for c in real)
            exp = "measure=%s lines=%s" % (("%.3f" % width).rstrip("0").rstrip("."), "|".join(oracle_wrap(adv, real, w)))
            if exp != line:
                bad += 1
                print("    case %r\n      want %s\n      got  %s" % (text, exp, line))
        report("measure and wrap (%d cases)" % len(CASES), "ok" if not bad else "FAIL", "%d differ" % bad if bad else "")
    finally:
        shutil.rmtree(work, ignore_errors=True)
    bad = [n for n, s in results if s == "FAIL"]
    print("\n%d ok, %d failed" % (sum(s == "ok" for _, s in results), len(bad)))
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()

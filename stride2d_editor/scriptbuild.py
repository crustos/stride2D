"""scriptbuild.py: building the project's C# scripts into the engine (no Qt here, so it can be tested without a display).

The scripts are C# in the subset the translator accepts (tools/ccsharp/README.md): a build writes them to a folder, runs tools/engine_so.py --scripts on it, which translates
engine + scripts to C and links a NEW libstride2d (a new file each time: a library already loaded under a name is not loaded again), and reads what the translator said:
errors come back as `File.cs(line,col): error CODE: message`, which the code editor shows in its problems list. The library's numbers for the scripts are in OUT.scripts.json.

A project's scripts can be in other languages (languages.py: C++, Rust and RPython, which Crust lowers to C). Every script is written to the folder under its language's
extension and tools/engine_so.py (tools/script_langs.py) tells them apart by it: it checks each language's scripts and says, as a warning, for each one whose language it
cannot build yet, so that nothing is left out unmentioned. What it says, and what the front ends of those languages say, is read here into Diagnostics:

    File.ext(line,col): error CODE: message         the C# translator's, and the tool's own (GEN0001 a script that is wrong, STRIDE0001 a language not built yet)
    cpprust: File.cpp:LINE: message                 C++ (tools/cpprust.py); `cpprust: message` alone has no place
    shivyc: error: crust: File.rs: line N: message  Rust's parser (crust, in shivyc), and `File.rs:LINE:COL: error: message` from the code it lowers
    SYNTAX ERROR in File.py: message (File.py, line N)   RPython (tools/py2c.py)
    File.c:LINE:COL: error: message                 the C compiler, on the C a front end wrote: that file is not the script, so the line is not its line and there is no place

Colour codes (shivyc writes them whether or not it is a terminal) are taken off first.
"""
import os
import re
import shutil
import subprocess
import sys
import tempfile

from . import languages

_HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(_HERE)

_ANSI = re.compile(r"\x1b\[[0-9;]*m")
_CPPRUST = re.compile(r"^cpprust:\s+(?P<file>[^\s:]+):(?P<line>\d+):\s*(?P<msg>.*)$")
_CPPRUST_PLAIN = re.compile(r"^cpprust:\s+(?P<msg>\S.*)$")
_CRUST = re.compile(r"^shivyc:\s+error:\s+crust:\s+(?P<file>\S+?):\s+line\s+(?P<line>\d+):\s*(?P<msg>.*)$")
_SHIVYC_PLAIN = re.compile(r"^shivyc:\s+(?P<sev>error|warning):\s+(?P<msg>\S.*)$")
_PLACED = re.compile(r"^(?P<file>[^\s:()]+):(?P<line>\d+):(?P<col>\d+):\s*(?P<sev>error|warning):\s*(?P<msg>.*)$")
_PY2C = re.compile(r"^\s*SYNTAX ERROR in (?P<file>\S+?):\s*(?P<msg>.*?)\s*\((?P<file2>[^,()]+),\s*line\s+(?P<line>\d+)\)\s*$")
_DIAG = re.compile(r"^(?P<file>[^\s(][^()]*?)\((?P<line>\d+),(?P<col>\d+)\):\s*(?P<sev>error|warning)\s*(?P<code>\w+)?:?\s*(?P<msg>.*)$")


class Diagnostic:
    def __init__(self, script, line, col, severity, code, message):
        self.script, self.line, self.col, self.severity, self.code, self.message = script, line, col, severity, code, message

    def __str__(self):
        where = ("%s:%d" % (self.script, self.line) if self.line else self.script) if self.script else ""
        return ("%s: " % where if where else "") + "%s%s: %s" % (self.severity, " " + self.code if self.code else "", self.message)


def file_name(name):
    """A script's file name (the name without its extension, made safe)."""
    return re.sub(r"[^A-Za-z0-9_]", "_", name) or "Script"


def script_of(path):
    """The script a source file is: its file name without the extension of a script's language, or None if it is not one (a generated .c, say)."""
    base = os.path.basename(path)
    lang = languages.by_extension(base)
    return base[:-len(lang.ext)] if lang else None


def parse_diagnostics(text):
    """The error and warning lines in `text` as Diagnostics (script = the file name without its extension), whichever tool said them (see the formats in the module's docstring);
    any other line that says `error` has no place."""
    out = []
    for raw in text.splitlines():
        line = _ANSI.sub("", raw).strip()
        m = _DIAG.match(line)
        if m:
            base = os.path.basename(m.group("file"))
            out.append(Diagnostic(script_of(base) or base, int(m.group("line")), int(m.group("col")), m.group("sev"), m.group("code") or "", m.group("msg")))
            continue
        m = _CPPRUST.match(line) or _CRUST.match(line) or _PY2C.match(line)
        if m and script_of(m.group("file")):
            out.append(Diagnostic(script_of(m.group("file")), int(m.group("line")), 1, "error", "", m.group("msg")))
            continue
        m = _PLACED.match(line)
        if m:
            name = script_of(m.group("file"))
            if name:                       # (the line is the script's: the compiler was shown the script itself, or lines that map to it)
                out.append(Diagnostic(name, int(m.group("line")), 1, m.group("sev"), "", m.group("msg")))
            else:                          # (a line of the C that a front end wrote, which is nobody's line: the message without a place, and where it was said)
                out.append(Diagnostic("", 0, 0, m.group("sev"), "", "%s (in the generated C, %s line %s)" % (m.group("msg"), os.path.basename(m.group("file")), m.group("line"))))
            continue
        m = _CPPRUST_PLAIN.match(line) or _SHIVYC_PLAIN.match(line)
        if m:
            out.append(Diagnostic("", 0, 0, m.groupdict().get("sev") or "error", "", m.group("msg")))
        elif re.search(r"\berror\b", line) and not line.startswith(("$", "==")):
            out.append(Diagnostic("", 0, 0, "error", "", line))
    return out


class BuildResult:
    def __init__(self, ok, lib=None, diagnostics=None, log="", scripts=None):
        self.ok, self.lib, self.diagnostics, self.log, self.scripts = ok, lib, diagnostics or [], log, scripts or {}


class Builder:
    """One per editor session: a work folder, and a count that makes each library's file name new."""

    def __init__(self, root=None):
        self.root = root or tempfile.mkdtemp(prefix="stride_scripts_")
        self.count = 0
        self.libs = []

    def prepare(self, project):
        """Writes the project's scripts to src/ and returns (the command to run, the library it will write)."""
        src = os.path.join(self.root, "src")
        shutil.rmtree(src, ignore_errors=True)
        os.makedirs(src)
        for f in project.scripts:
            with open(os.path.join(src, file_name(f.name) + f.ext), "w", encoding="utf-8", newline="\n") as fh:
                fh.write(f.text)
        self.count += 1
        lib = os.path.join(self.root, "libstride2d_%d.so" % self.count)
        cmd = [sys.executable, os.path.join(ROOT, "tools", "engine_so.py"), "--scripts", src, "--work", os.path.join(self.root, "work"), "-o", lib]
        return cmd, lib

    def finish(self, lib, returncode, output):
        """The result of the command `prepare` gave, once it has run."""
        diags = parse_diagnostics(output)
        if returncode == 0 and os.path.exists(lib):
            import json
            try:
                with open(lib + ".scripts.json", encoding="utf-8") as f:
                    scripts = {item["name"]: int(item["id"]) for item in json.load(f)}
            except (OSError, ValueError, KeyError):
                scripts = {}
            self.libs.append(lib)
            return BuildResult(True, lib, diags, output, scripts)
        if not any(d.severity == "error" for d in diags):
            diags = [Diagnostic("", 0, 0, "error", "", "the build failed: " + (output.strip().splitlines() or ["no output"])[-1])] + diags
        return BuildResult(False, None, diags, output)

    def build(self, project):
        """Synchronous: prepare, run, finish."""
        cmd, lib = self.prepare(project)
        r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
        return self.finish(lib, r.returncode, r.stdout + r.stderr)

    def forget_old(self, keep):
        """Deletes the libraries of earlier builds except `keep` (and the ones still loaded must not be passed here)."""
        for lib in list(self.libs):
            if lib != keep:
                for path in (lib, lib + ".scripts.json"):
                    try:
                        os.remove(path)
                    except OSError:
                        pass
                self.libs.remove(lib)

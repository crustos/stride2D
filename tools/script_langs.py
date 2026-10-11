#!/usr/bin/env python3
"""script_langs.py -- the script languages beside C#, as the build sees them (the editor's own table of them is stride2d_editor/languages.py).

A project's scripts are files in a folder; the file's extension says what language it is (.cs C#, .cpp C++, .rs Rust, .py RPython). tools/engine_so.py --scripts DIR
builds the C# ones into the engine with CC#, and for every other language asks this module what scripts the files hold:

    scan_file(path, language)   the script classes of one file, as dicts: name, language, capacity, callbacks (canonical C# spellings: Update, OnTriggerEnter2D ...), line, where
    scan_folder(folder)         the same for every file of the folder that is not C#, and the errors as compiler-style lines
    unbuilt_notes(scripts)      a warning per script whose language the build cannot turn into engine code yet

What a scan checks is what tools/ccsharp/gen_scripts.py checks of a C# script, in each language's own spelling, because a script that is almost right is a script that silently
never runs:

    marker + capacity     C++  STRIDE_SCRIPT(16) class Name { ... }          Rust  #[script(max_instances = 16)] struct Name { .. } with `impl Name { fn update(&mut self) .. }`
                          RPython  @script(max_instances=16) class Name(object): .. def update(self): ..      the capacity is an integer literal of at least 1
    callbacks             the names of the C# callbacks, as C++ methods in the same spelling (`void Update()`, public), as Rust and RPython methods in snake_case (`update`,
                          `on_trigger_enter_2d`). One that is declared but would never be called (not void, not public, no `&mut self`, no `self`) is an error, and so is a
                          lifecycle callback (Start, Update, ...) with parameters
    names                 two scripts with one name are an error across all languages, since sprites and the game attach by name

An error is raised as gen_scripts.GenError("FILE:LINE: message"), and scan_folder returns it as `File.ext(LINE,1): error GEN0001: message`, the format the editor's problems list reads.
This module only reads the files. What is done with the scripts of a language that is built is that language's own step (BUILT says which are).
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import gen_scripts   # noqa: E402

GenError = gen_scripts.GenError

EXTENSIONS = {".cs": "csharp", ".cpp": "cpp", ".rs": "rust", ".py": "rpython"}
NAMES = {"csharp": "C#", "cpp": "C++", "rust": "Rust", "rpython": "RPython"}
BUILT = ("csharp", "cpp", "rust", "rpython")                     # the languages the build turns into engine code (one not in it is scanned, and said not to be built yet); tools/script_native.py builds the others

CALLBACKS = [c[0] for c in gen_scripts.CALLBACKS]
LIFECYCLE = ["OnEnable", "OnDisable", "Start", "FixedUpdate", "Update", "LateUpdate"]       # the callbacks that take nothing
SNAKE = {"OnEnable": "on_enable", "OnDisable": "on_disable", "Start": "start", "FixedUpdate": "fixed_update", "Update": "update", "LateUpdate": "late_update",
         "OnCollisionBegin2D": "on_collision_begin_2d", "OnCollisionEnd2D": "on_collision_end_2d", "OnTriggerEnter2D": "on_trigger_enter_2d",
         "OnTriggerStay2D": "on_trigger_stay_2d", "OnTriggerExit2D": "on_trigger_exit_2d"}
assert sorted(SNAKE) == sorted(CALLBACKS)


def spelling(language, canonical):
    """How `language` spells the callback the C# engine calls `canonical`."""
    return SNAKE[canonical] if language in ("rust", "rpython") else canonical


def language_of(path):
    """The language a file is in, by its extension, or None."""
    return EXTENSIONS.get(os.path.splitext(path)[1].lower())


def _line_of(text, pos):
    return text.count("\n", 0, pos) + 1


def _capacity(value, name, where, how):
    if value is None or not re.fullmatch(r"\d+", value.strip()):
        raise GenError("%s: script %s needs %s with N an integer literal" % (where, name, how))
    n = int(value)
    if n < 1:
        raise GenError("%s: script %s: the capacity must be at least 1" % (where, name))
    return n


def _which(callbacks):
    return [c for c in CALLBACKS if c in callbacks]


def _top_level(body):
    """`body` (the inside of a class or impl) with everything inside a nested { } blanked, every offset and newline kept: what is left is the members' heads, so a call to Update()
    in a method's body is not taken for a declaration of it, and a callback is found wherever on its line it is written."""
    out, depth = [], 0
    for ch in body:
        if ch == "{":
            depth += 1
            out.append(ch)
        elif ch == "}":
            depth = max(0, depth - 1)
            out.append(ch)
        else:
            out.append(ch if depth == 0 or ch == "\n" else " ")
    return "".join(out)


# ---- C++

def _scan_cpp(path, raw):
    text = gen_scripts.strip_comments(raw)
    use = re.compile(r"STRIDE_SCRIPT\s*\(\s*([^)]*?)\s*\)\s*(class|struct)\s+(\w+)\s*(?::[^{;]*)?\{")
    scripts = []
    for m in re.finditer(r"\bSTRIDE_SCRIPT\b", text):
        line_start = text.rfind("\n", 0, m.start()) + 1
        if text[line_start:m.start()].lstrip().startswith("#"):                 # (#define STRIDE_SCRIPT(n): the macro itself, not a use of it)
            continue
        where = "%s:%d" % (path, _line_of(text, m.start()))
        u = use.match(text, m.start())
        if not u:
            raise GenError("%s: STRIDE_SCRIPT(N) must come directly before a class: STRIDE_SCRIPT(16) class Name { ... }" % where)
        name = u.group(3)
        capacity = _capacity(u.group(1), name, where, "STRIDE_SCRIPT(N)")
        is_struct = u.group(2) == "struct"
        body, _ = gen_scripts.body_of(text, u.end() - 1)
        body = _top_level(body)
        base = u.end()                                                            # (where `body` starts in `text`: an error points at the declaration's own line)
        access = [(am.start(), am.group(1)) for am in re.finditer(r"\b(public|private|protected)\s*:", body)]

        def public_at(pos):
            kind = "public" if is_struct else "private"
            for at, k in access:
                if at < pos:
                    kind = k
            return kind == "public"
        has = set()
        for cb in CALLBACKS:
            for d in re.finditer(r"(?<![\w:<>*&])([A-Za-z_][\w:<>*&]*)\s+%s\s*\(([^)]*)\)" % cb, body):
                at = "%s:%d" % (path, _line_of(text, base + d.start()))
                if d.group(1) != "void":
                    raise GenError("%s: script %s: %s must return void, or it would never be called" % (at, name, cb))
                if not public_at(d.start()):
                    raise GenError("%s: script %s: %s is not public, so it would never be called" % (at, name, cb))
                if cb in LIFECYCLE and d.group(2).strip() not in ("", "void"):
                    raise GenError("%s: script %s: %s takes no parameters" % (at, name, cb))
                if cb not in LIFECYCLE and not re.fullmatch(r"int(\s+\w+)?", d.group(2).strip()):
                    raise GenError("%s: script %s: %s takes the other node's handle: `void %s(int other)`" % (at, name, cb, cb))
                has.add(cb)
        if not re.search(r"\bint\s+node\s*;", _top_level(body)):
            raise GenError("%s: script %s needs a member `int node;` (the engine sets it to the node's handle)" % (where, name))
        scripts.append(dict(name=name, language="cpp", capacity=capacity, callbacks=_which(has), line=_line_of(text, m.start()), where=where))
    return scripts


# ---- Rust

def _scan_rust(path, raw):
    text = gen_scripts.strip_comments(raw)
    use = re.compile(r"#\[\s*script\b\s*(?:\(([^)]*)\))?\s*\]\s*(?:#\[[^\]]*\]\s*)*(?:pub(?:\([^)]*\))?\s+)?struct\s+(\w+)")
    scripts = []
    for m in re.finditer(r"#\[\s*script\b", text):
        where = "%s:%d" % (path, _line_of(text, m.start()))
        u = use.match(text, m.start())
        if not u:
            raise GenError("%s: #[script(max_instances = N)] must come directly before a struct" % where)
        name = u.group(2)
        cap = re.search(r"\bmax_instances\s*=\s*([^,)\s]+)", u.group(1) or "")
        capacity = _capacity(cap.group(1) if cap else None, name, where, "#[script(max_instances = N)]")
        has = set()
        for im in re.finditer(r"\bimpl\s+%s\s*\{" % re.escape(name), text):
            body, _ = gen_scripts.body_of(text, im.end() - 1)
            body = _top_level(body)
            for cb in CALLBACKS:
                for d in re.finditer(r"\bfn\s+%s\s*\(([^)]*)\)" % SNAKE[cb], body):
                    at = "%s:%d" % (path, _line_of(text, im.end() + d.start()))
                    params = [p.strip() for p in d.group(1).split(",") if p.strip()]
                    if not params or not re.fullmatch(r"&\s*(?:mut\s+)?self", params[0]):
                        raise GenError("%s: script %s: %s must take `&mut self`, or it would never be called" % (at, name, SNAKE[cb]))
                    if cb in LIFECYCLE and len(params) != 1:
                        raise GenError("%s: script %s: %s takes no parameters besides `&mut self`" % (at, name, SNAKE[cb]))
                    if cb not in LIFECYCLE and (len(params) != 2 or not re.fullmatch(r"\w+\s*:\s*i32", params[1])):
                        raise GenError("%s: script %s: %s takes the other node's handle: `fn %s(&mut self, other: i32)`" % (at, name, SNAKE[cb], SNAKE[cb]))
                    has.add(cb)
        sb = re.compile(r"\bstruct\s+%s\s*\{" % re.escape(name)).search(text)
        if sb and not re.search(r"\bnode\s*:\s*i32\b", gen_scripts.body_of(text, sb.end() - 1)[0]):
            raise GenError("%s: script %s needs a field `node: i32` (the engine sets it to the node's handle)" % (where, name))
        scripts.append(dict(name=name, language="rust", capacity=capacity, callbacks=_which(has), line=_line_of(text, m.start()), where=where))
    return scripts


# ---- RPython

def _strip_python(text):
    """`text` with comments and the insides of strings blanked, every offset and newline kept, so a regex never matches inside them."""
    out, i, n = [], 0, len(text)
    while i < n:
        c = text[i]
        if c == "#":
            j = text.find("\n", i)
            j = n if j < 0 else j
            out.append(" " * (j - i))
            i = j
        elif c in "\"'":
            q = text[i:i + 3] if text[i:i + 3] in ('"""', "'''") else c
            j = i + len(q)
            while j < n and not text.startswith(q, j):
                if len(q) == 1 and text[j] == "\n":
                    break
                j += 2 if text[j] == "\\" else 1
            end = min(n, j + len(q)) if text.startswith(q, j) else j
            out.append(q + re.sub(r"[^\n]", " ", text[i + len(q):j]) + (q if text.startswith(q, j) else ""))
            i = end
        else:
            out.append(c)
            i += 1
    return "".join(out)


def _scan_rpython(path, raw):
    text = _strip_python(raw)
    lines = text.split("\n")
    scripts = []
    for n, ln in enumerate(lines):
        dm = re.match(r"^([ \t]*)@script\b(?:\(([^)]*)\))?[ \t]*$", ln)
        if not dm:
            continue
        where = "%s:%d" % (path, n + 1)
        k = n + 1
        while k < len(lines) and re.match(r"^[ \t]*@", lines[k]):                # (more decorators between)
            k += 1
        cm = re.match(r"^([ \t]*)class\s+(\w+)\s*(?:\([^)]*\))?\s*:", lines[k]) if k < len(lines) else None
        if not cm:
            raise GenError("%s: @script(max_instances=N) must come directly before a class" % where)
        name = cm.group(2)
        args = (dm.group(2) or "").strip()
        km = re.search(r"\bmax_instances\s*=\s*([^,)\s]+)", args)
        capacity = _capacity(km.group(1) if km else (args if re.fullmatch(r"\d+", args) else None), name, where, "@script(max_instances=N)")
        indent = len(cm.group(1).expandtabs(4))
        body = []
        for ln2 in lines[k + 1:]:
            if ln2.strip() and len(ln2) - len(ln2.lstrip()) <= indent:
                break
            body.append(ln2)
        own = min([len(b) - len(b.lstrip()) for b in body if b.strip()] or [0])                    # (a def deeper than the class body's own indent is a nested function)
        joined = "\n".join(body)
        has = set()
        for cb in CALLBACKS:
            for d in re.finditer(r"^[ \t]{%d}def\s+%s\s*\(([^)]*)\)" % (own, SNAKE[cb]), joined, re.M):
                at = "%s:%d" % (path, k + 2 + joined.count("\n", 0, d.start()))          # (the body starts on the line after the class line, k + 1 counting from 0)
                params = [p.strip() for p in d.group(1).split(",") if p.strip()]
                if not params or params[0] != "self":
                    raise GenError("%s: script %s: %s must take `self`, or it would never be called" % (at, name, SNAKE[cb]))
                if cb in LIFECYCLE and len(params) != 1:
                    raise GenError("%s: script %s: %s takes no parameters besides `self`" % (at, name, SNAKE[cb]))
                if cb not in LIFECYCLE and (len(params) != 2 or not re.fullmatch(r"\w+\s*:\s*int", params[1])):
                    raise GenError("%s: script %s: %s takes the other node's handle: `def %s(self, other: int)`" % (at, name, SNAKE[cb], SNAKE[cb]))
                has.add(cb)
        if not re.search(r"\bself\.node\s*:\s*int\b", joined):
            raise GenError("%s: script %s needs `self.node: int = 0` in __init__ (the engine sets it to the node's handle; the annotation gives the field its C type)" % (where, name))
        scripts.append(dict(name=name, language="rpython", capacity=capacity, callbacks=_which(has), line=n + 1, where=where))
    return scripts


SCANNERS = {"cpp": _scan_cpp, "rust": _scan_rust, "rpython": _scan_rpython}


def scan_file(path, language=None):
    """The script classes of one file in C++, Rust or RPython (the language, if not given, from the extension), or GenError("FILE:LINE: message")."""
    language = language or language_of(path)
    if language not in SCANNERS:
        raise GenError("%s: no scanner for %s files" % (path, NAMES.get(language, language)))
    with open(path, encoding="utf-8-sig") as f:
        raw = f.read()
    return SCANNERS[language](path, raw)


def diagnostic(base, message):
    """GenError text `FILE:LINE: message` as the compiler-style line the editor reads: `File.ext(LINE,1): error GEN0001: message`."""
    m = re.match(r"(.*?):(\d+):\s*(.*)", message, re.S)
    line, text = (int(m.group(2)), m.group(3)) if m else (1, message)
    return "%s(%d,1): error GEN0001: %s" % (base, line, text.replace("\n", " "))


def scan_folder(folder):
    """The scripts of every file in `folder` that is not C#: (scripts, errors), errors as compiler-style lines (all of them: one file's mistake does not hide another's)."""
    scripts, errors = [], []
    for fn in sorted(os.listdir(folder)):
        lang = language_of(fn)
        if lang is None or lang == "csharp":
            continue
        try:
            scripts += scan_file(os.path.join(folder, fn), lang)
        except GenError as e:
            errors.append(diagnostic(fn, str(e)))
    return scripts, errors


def unbuilt_notes(scripts):
    """A warning line for each script whose language is not built into the engine yet, at the line of its marker."""
    return ["%s(%d,1): warning STRIDE0001: %s scripts are not built yet: %s will not run"
            % (os.path.basename(s["where"].rsplit(":", 1)[0]), s["line"], NAMES[s["language"]], s["name"]) for s in scripts if s["language"] not in BUILT]

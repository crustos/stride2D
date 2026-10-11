"""languages.py: the languages a project's scripts can be written in (no Qt here, so the model, the builder and the tests can use it without a display).

A script is one file in one language. What the editor needs to know about a language is gathered in one `Language`:

  id, name, ext   what the project file calls it ("cpp"), what the menus call it ("C++"), and the file the build writes the script to (".cpp")
  template        a new script: a file with one script class, with the class's name in it as %(name)s
  classes(text)   the script classes of a file. A class is a script when it carries the language's marker, and attaching (sprites, the game) is by that class name:

                    csharp    [Script, MaxInstances(16)] class Name                       (Native/Engine2D, tools/ccsharp/gen_scripts.py)
                    cpp       STRIDE_SCRIPT(16) class Name                                 (a macro that expands to nothing: cpprust never sees it)
                    rust      #[script(max_instances = 16)] struct Name                   (Crust skips item attributes)
                    rpython   @script(max_instances=16) class Name                        (a decorator; from stride2d import script)

                  Each marker was run through its front end (tools/cpprust.py, shivyc/crust.py, tools/py2c.py) to see that it is accepted and changes nothing.
  the syntax      keywords, types, comments and a few more patterns, as data: gui_scripts.py colours a file from them

The C++, Rust and RPython scripts are lowered to C by Crust (the same C the engine is) and linked into the engine library; see scriptbuild.py for what the
build does with each language, and tools/script_native.py for how each is built. A script reaches the engine through node handles (an int), not through the C# engine's Component and Node objects.
"""
import re


class UnknownLanguage(ValueError):
    pass


# ---- C# (the first, and what every project written before there were languages is)

CSHARP_KEYWORDS = ("abstract as base bool break byte case catch char checked class const continue decimal default delegate do double else enum event explicit extern false finally "
                   "fixed float for foreach goto if implicit in int interface internal is lock long namespace new null object operator out override params private protected public "
                   "readonly ref return sbyte sealed short sizeof static string struct switch this throw true try typeof uint ulong unchecked unsafe ushort using var virtual void "
                   "volatile while").split()
CSHARP_TYPES = "Component Node Scene2D Rigidbody2D Collider2D Collision2D Input2D Script MaxInstances Console Math Mathf".split()

CSHARP_CLASS = re.compile(r"\[\s*Script\b[^\]]*\]\s*(?:\[[^\]]*\]\s*)*(?:(?:public|internal)\s+)?(?:sealed\s+)?class\s+(\w+)")

CSHARP_TEMPLATE = """using System;
using Stride2D;

// A script: C# that runs on a node while the level plays.
// Keep to the C# subset (no lambdas, try/catch, ...): Build says where a line does not fit.
// Callbacks: Start, Update, FixedUpdate, LateUpdate, OnEnable, OnDisable,
//   OnCollisionBegin2D(Collision2D hit), OnCollisionEnd2D(Collision2D hit),
//   OnTriggerEnter2D(Collider2D other), OnTriggerStay2D, OnTriggerExit2D.
// Input: Input2D.Key(Input2D.Left), Input2D.Key('A'), Input2D.MouseX, Input2D.MouseDown(0).
[Script, MaxInstances(16)]
class %(name)s
{
    public Component Self;
    public float Time;

    public void Update()
    {
        Time += 1f / 60f;
        // Self.Node.SetPosition(Self.Node.WorldX() + 0.02f, Self.Node.WorldY());
    }
}
"""

# ---- C++ (the Crust subset)

CPP_KEYWORDS = ("alignas alignof auto bool break case catch char class const constexpr continue decltype default delete do double else enum explicit extern false float for friend "
                "goto if inline int long mutable namespace new noexcept nullptr operator override private protected public register return short signed sizeof static "
                "static_assert struct switch template this throw true try typedef typename union unsigned using virtual void volatile while").split()
CPP_TYPES = "int8_t int16_t int32_t int64_t uint8_t uint16_t uint32_t uint64_t size_t string vector map unique_ptr shared_ptr STRIDE_SCRIPT".split()

CPP_CLASS = re.compile(r"\bSTRIDE_SCRIPT\s*\(\s*\d*\s*\)\s*(?:class|struct)\s+(\w+)")

CPP_TEMPLATE = """// A script: C++ (the Crust subset) that runs on a node while the level plays.
// Keep to the subset: Build says where a line does not fit.
// STRIDE_SCRIPT(n) marks the class and says how many can exist at once. `node` is the handle of the node the script runs on; the engine's calls take it.
// Callbacks, all optional: Start, Update, FixedUpdate, LateUpdate, OnEnable, OnDisable,
//   OnCollisionBegin2D(int other), OnCollisionEnd2D(int other) (HitX(), HitNY() ... say where), OnTriggerEnter2D(int other), OnTriggerStay2D, OnTriggerExit2D.
// Engine: SetPos, NodeX, NodeY, AddBody, SetVelocity, Impulse ...  Input: KeyDown('A'), MouseDown(0), MouseWorldX(), MouseWorldY().
#include "stride2d.h"

STRIDE_SCRIPT(16)
class %(name)s {
public:
    int node;
    float time;

    void Update() {
        time += 1.0f / 60.0f;
        // SetPos(node, NodeX(node) + 0.02f, NodeY(node));
    }
};
"""

# ---- Rust (the Crust subset)

RUST_KEYWORDS = ("as break const continue crate dyn else enum extern false fn for if impl in let loop match mod move mut pub ref return self Self static struct super trait "
                 "true type unsafe use where while").split()
RUST_TYPES = "i8 i16 i32 i64 isize u8 u16 u32 u64 usize f32 f64 bool char str String Vec Option Box".split()

RUST_CLASS = re.compile(r"#\[\s*script\b[^\]]*\]\s*(?:#\[[^\]]*\]\s*)*(?:pub(?:\([^)]*\))?\s+)?struct\s+(\w+)")

RUST_TEMPLATE = """// A script: Rust (the Crust subset) that runs on a node while the level plays.
// Keep to the subset: Build says where a line does not fit.
// #[script(max_instances = n)] marks the struct and says how many can exist at once. `node` is the handle of the node the script runs on; the engine's calls take it.
// Callbacks, all optional, in an `impl` of the struct: start, update, fixed_update, late_update, on_enable, on_disable,
//   on_collision_begin_2d(&mut self, other: i32), on_collision_end_2d (hit_x(), hit_ny() ... say where), on_trigger_enter_2d(&mut self, other: i32), on_trigger_stay_2d, on_trigger_exit_2d.
// Engine: set_pos, node_x, node_y, add_body, set_velocity, impulse ...  Input: key_down(65), mouse_down(0), mouse_world_x(), mouse_world_y().
use stride2d::*;

#[script(max_instances = 16)]
struct %(name)s {
    node: i32,
    time: f32,
}

impl %(name)s {
    fn update(&mut self) {
        self.time += 1.0 / 60.0;
        // set_pos(self.node, node_x(self.node) + 0.02, node_y(self.node));
    }
}
"""

# ---- RPython (the Crust Python subset)

RPYTHON_KEYWORDS = ("and as assert break class continue def del elif else except finally for from global if import in is lambda nonlocal not or pass raise return try while "
                    "with yield True False None").split()
RPYTHON_TYPES = "self object int float str bool list dict tuple range len print isinstance script".split()

RPYTHON_CLASS = re.compile(r"^[ \t]*@script\b(?:\([^)\n]*\))?[ \t]*\n(?:[ \t]*@[^\n]*\n)*[ \t]*class[ \t]+(\w+)", re.M)

RPYTHON_TEMPLATE = """# A script: RPython (the Crust Python subset) that runs on a node while the level plays.
# Keep to the subset: Build says where a line does not fit.
# @script(max_instances=n) marks the class and says how many can exist at once. `node` is the handle of the node the script runs on; the engine's calls take it.
# Callbacks, all optional: start, update, fixed_update, late_update, on_enable, on_disable,
#   on_collision_begin_2d(self, other: int), on_collision_end_2d (hit_x(), hit_ny() ... say where), on_trigger_enter_2d(self, other: int), on_trigger_stay_2d, on_trigger_exit_2d.
# Engine: set_pos, node_x, node_y, add_body, set_velocity, impulse ...  Input: key_down(65), mouse_down(0), mouse_world_x(), mouse_world_y().
# Annotate fields (`self.x: float = 0.0`): that is what gives them C types. __init__ runs when the script is attached.
from stride2d import script


@script(max_instances=16)
class %(name)s:
    def __init__(self):
        self.node: int = 0
        self.time: float = 0.0

    def update(self):
        self.time += 1.0 / 60.0
        # set_pos(self.node, node_x(self.node) + 0.02, node_y(self.node))
"""


def _strip_c_comments(text):
    """`text` without // and /* */ comments (a comment becomes a space, so what is left still reads as separate words)."""
    return re.sub(r"//[^\n]*", " ", re.sub(r"/\*.*?\*/", " ", text, flags=re.S))


def _strip_c_line_comments(text):
    return re.sub(r"//[^\n]*", "", text)


def _strip_hash_comments(text):
    return re.sub(r"(?m)#[^\n]*$", "", text)


class Language:
    def __init__(self, id, name, ext, template, pattern, strip, keywords, types, line_comment, block=None, block_is_string=False, extra=(), char_pattern=None,
                 number=r"\b\d+(\.\d+)?f?\b", indent_after="{"):
        self.id, self.name, self.ext, self.template = id, name, ext, template
        self.pattern = pattern                  # finds the script classes (group 1 is the name) in text that `strip` has cleaned
        self.strip = strip
        # how the code editor colours it
        self.keywords, self.types = keywords, types
        self.line_comment = line_comment        # what starts a comment that runs to the end of the line
        self.block = block                      # (start, end) of what can run over lines, or None
        self.block_is_string = block_is_string  # a block that is a string (Python's triple quotes) rather than a comment
        self.extra = list(extra)                # [(regex, colour)] more patterns (attributes, decorators, preprocessor lines), coloured before strings and comments
        self.char_pattern = char_pattern or r"'(\\.|[^'\\])*'"
        self.number = number
        self.indent_after = indent_after        # what at the end of a line makes the next one indent: "{" or ":"

    def new_text(self, name):
        """A new script file whose class is `name`."""
        return self.template % {"name": name}

    def classes(self, text):
        """The names of the script classes in `text`, in file order."""
        return self.pattern.findall(self.strip(text))


CSHARP = Language("csharp", "C#", ".cs", CSHARP_TEMPLATE, CSHARP_CLASS, _strip_c_line_comments, CSHARP_KEYWORDS, CSHARP_TYPES, "//", block=("/*", "*/"),
                  extra=[(r"\[[A-Za-z_][^\]\n]*\]", "#dcdcaa")])
CPP = Language("cpp", "C++", ".cpp", CPP_TEMPLATE, CPP_CLASS, _strip_c_comments, CPP_KEYWORDS, CPP_TYPES, "//", block=("/*", "*/"),
               extra=[(r"^\s*#\s*\w+", "#dcdcaa")], number=r"\b\d+(\.\d+)?[fFuUlL]*\b")
RUST = Language("rust", "Rust", ".rs", RUST_TEMPLATE, RUST_CLASS, _strip_c_comments, RUST_KEYWORDS, RUST_TYPES, "//", block=("/*", "*/"),
                extra=[(r"#!?\[[^\]\n]*\]", "#dcdcaa")], char_pattern=r"'(\\.[^']*|[^'\\])'", number=r"\b\d[\d_]*(\.\d+)?(f32|f64|[iu](8|16|32|64|size))?\b")
RPYTHON = Language("rpython", "RPython", ".py", RPYTHON_TEMPLATE, RPYTHON_CLASS, _strip_hash_comments, RPYTHON_KEYWORDS, RPYTHON_TYPES, "#", block=('"""', '"""'),
                   block_is_string=True, extra=[(r"^\s*@\w+", "#dcdcaa")], number=r"\b\d+(\.\d+)?\b", indent_after=":")

DEFAULT = "csharp"
LANGUAGES = {l.id: l for l in (CSHARP, CPP, RUST, RPYTHON)}      # in the order the menus list them


def get(id):
    """The Language called `id` ("csharp", "cpp", "rust", "rpython")."""
    try:
        return LANGUAGES[id]
    except (KeyError, TypeError):
        raise UnknownLanguage("unknown script language %r (known: %s)" % (id, ", ".join(LANGUAGES)))


def by_extension(path):
    """The Language whose files end like `path`, or None."""
    p = str(path).lower()
    for l in LANGUAGES.values():
        if p.endswith(l.ext):
            return l
    return None

"""The consume demo talks to the platform over REST, and by no other route.

WHY THIS TEST EXISTS

`apps/consume-demo` is a demonstration that an external agent, workflow or
Copilot integration can put a case to a project's published policies knowing
nothing but a base URL, a project key and a token. That claim is only worth
making if it is *true of the demo itself*. The moment the playground imports a
type from `apps/web`, reads a value out of `policy_platform`, or reaches a
database, it stops being evidence about the API and becomes a second front end
of the product wearing a different name -- and nobody looking at it can tell,
because the screen looks identical either way.

So the isolation is asserted rather than intended. Each of the three ways it
would realistically be lost has its own test:

  * an import or an alias that reaches out of the app directory,
  * a dependency on a workspace package or a path outside it,
  * a credential written somewhere that outlives the tab.

WHAT THIS TEST DELIBERATELY DOES NOT DO

It does not police the app's design, its copy, or its behaviour -- those are
asserted by the app's own vitest suite, which can render it. This file asserts
only the architectural boundary, which is the one property the app cannot check
about itself from the inside.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
_APP = _ROOT / "apps" / "consume-demo"

#: Directories inside the app that are not ours to police.
_SKIP = ("node_modules", "dist", "build", ".vite")


def _app_files(*suffixes: str) -> list[Path]:
    """Every source file we wrote, and none that a tool generated."""

    found: list[Path] = []
    for suffix in suffixes:
        for path in _APP.rglob(f"*{suffix}"):
            if any(part in _SKIP for part in path.relative_to(_APP).parts):
                continue
            found.append(path)
    return sorted(found)


def _source_files() -> list[Path]:
    return _app_files(".ts", ".tsx")


def _rel(path: Path) -> str:
    return path.relative_to(_ROOT).as_posix()


_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)
_LINE_COMMENT = re.compile(r"(?m)^\s*//.*$")


def _code_only(text: str) -> str:
    """The file with its comments removed.

    Needed because the modules being guarded *explain* what they must not do --
    "never written to `localStorage`" is exactly the sentence a reviewer wants
    to find, and a substring guard that fires on the explanation punishes the
    documentation and rewards silence.
    """

    return _LINE_COMMENT.sub("", _BLOCK_COMMENT.sub("", text))


def test_the_app_exists_where_it_is_documented_to():
    """A guard over a directory that moved is a guard over nothing."""

    assert _APP.is_dir(), f"{_rel(_APP)} is missing; this guard has nothing to check"
    assert (_APP / "package.json").is_file(), "the demo has no manifest of its own"
    assert _source_files(), "no TypeScript sources found -- the guard would pass vacuously"


# ── the boundary ─────────────────────────────────────────────────────

#: Module specifiers that would mean this app is not standalone. Matched
#: against the string inside an `import ... from '<here>'`, a bare
#: `import '<here>'`, a dynamic `import('<here>')` or a `require('<here>')`.
_FORBIDDEN_SPECIFIERS = (
    # The product's other front end. Sharing a component is how two apps become
    # one app with two entry points.
    "apps/web",
    "@web/",
    # The platform's Python package, reachable through a bundler alias or a
    # generated client. Either way it is not something an external caller has.
    "policy_platform",
    "policy-platform",
    # Anything at all above this app's own directory.
    "../../",
)

#: Packages that would give the page a way to reach data other than by HTTP.
_FORBIDDEN_DEPENDENCIES = (
    "pg",
    "postgres",
    "sqlite3",
    "better-sqlite3",
    "mysql",
    "mysql2",
    "sequelize",
    "typeorm",
    "prisma",
    "@prisma/client",
    "knex",
    "mongodb",
    "mongoose",
    "redis",
    "ioredis",
)

_IMPORT_PATTERN = re.compile(
    r"""(?:
          from\s+['"](?P<from>[^'"]+)['"]
        | import\s+['"](?P<bare>[^'"]+)['"]
        | import\s*\(\s*['"](?P<dynamic>[^'"]+)['"]\s*\)
        | require\s*\(\s*['"](?P<require>[^'"]+)['"]\s*\)
        )""",
    re.VERBOSE,
)


def _specifiers(text: str) -> list[str]:
    return [
        value
        for match in _IMPORT_PATTERN.finditer(text)
        for value in match.groupdict().values()
        if value
    ]


@pytest.mark.parametrize("source", _source_files(), ids=_rel)
def test_no_source_file_imports_across_the_boundary(source: Path):
    """Nothing in the demo may import the product, or anything above itself."""

    for specifier in _specifiers(_code_only(source.read_text(encoding="utf-8"))):
        for forbidden in _FORBIDDEN_SPECIFIERS:
            assert forbidden not in specifier, (
                f"{_rel(source)} imports {specifier!r}, which reaches {forbidden!r}. "
                "The playground demonstrates that the REST API is sufficient; an "
                "import that leaves this directory makes it demonstrate the opposite."
            )

        # A relative import must resolve inside the app. `./` and `../` within
        # src are fine; anything that climbs out of apps/consume-demo is not.
        if specifier.startswith("."):
            resolved = (source.parent / specifier).resolve()
            assert _APP.resolve() in resolved.parents or resolved == _APP.resolve(), (
                f"{_rel(source)} imports {specifier!r}, which resolves to "
                f"{resolved} -- outside {_rel(_APP)}."
            )


def test_the_typescript_config_declares_no_path_alias():
    """An alias is the usual way a "separate" app starts sharing source.

    `paths` is checked rather than assumed empty because an alias is invisible
    at the import site: `import { api } from "@product/api"` looks like a
    package and is a symlink into the other app.
    """

    config = (_APP / "tsconfig.app.json").read_text(encoding="utf-8")
    # tsconfig permits comments, so the file is scanned rather than parsed.
    aliases = re.search(r'"paths"\s*:\s*\{(?P<body>[^}]*)\}', config)
    assert aliases is not None, "tsconfig.app.json should state `paths` explicitly, even as {}"
    assert not aliases.group("body").strip(), (
        f"tsconfig.app.json declares path aliases: {aliases.group('body')!r}. "
        "The demo must resolve every import as a real package or a real relative path."
    )


def test_the_vite_config_declares_no_alias_and_owns_its_port():
    vite = (_APP / "vite.config.ts").read_text(encoding="utf-8")
    assert "resolve:" not in vite or "alias" not in vite, (
        "vite.config.ts declares a resolve alias; an alias out of this directory "
        "is an import out of this directory with a friendlier spelling."
    )
    assert "port: 5179" in vite, "the demo is documented to serve on 5179"
    assert "strictPort: true" in vite, (
        "without strictPort the demo silently moves to another port, which the "
        "API's CORS allowlist will not recognise -- and a CORS block looks like "
        "a broken backend rather than a port collision"
    )


# ── dependencies ─────────────────────────────────────────────────────


def test_the_app_has_its_own_manifest_and_lockfile():
    """Own dependencies, own lockfile, no workspace membership.

    A workspace entry would hoist this app's `node_modules` into the repository
    root and let it resolve anything another package installed -- which is a
    shared dependency tree wearing the words "separate app".
    """

    manifest = json.loads((_APP / "package.json").read_text(encoding="utf-8"))
    assert manifest["name"] == "consume-demo"
    assert manifest.get("private") is True
    assert "workspaces" not in manifest, "the demo must not open a workspace of its own"
    assert (_APP / "package-lock.json").is_file(), "the demo needs its own lockfile"

    root_manifest = _ROOT / "package.json"
    if root_manifest.is_file():
        root = json.loads(root_manifest.read_text(encoding="utf-8"))
        assert "workspaces" not in root, (
            "a root workspace would hoist apps/consume-demo's dependencies and "
            "dissolve the boundary this test exists to hold"
        )


def test_no_dependency_gives_the_page_a_route_to_data_other_than_http():
    manifest = json.loads((_APP / "package.json").read_text(encoding="utf-8"))
    declared = {
        **manifest.get("dependencies", {}),
        **manifest.get("devDependencies", {}),
    }

    for name in declared:
        assert name not in _FORBIDDEN_DEPENDENCIES, (
            f"apps/consume-demo depends on {name!r}. The playground reaches the "
            "platform over HTTP only; a database client in a browser demo is "
            "either dead weight or a second, unaudited path to the data."
        )
        assert not name.startswith("@policy-platform/"), (
            f"apps/consume-demo depends on the product package {name!r}"
        )


def test_no_dependency_is_resolved_from_a_local_path():
    """`file:` and `link:` are imports with a package.json around them."""

    manifest = json.loads((_APP / "package.json").read_text(encoding="utf-8"))
    declared = {
        **manifest.get("dependencies", {}),
        **manifest.get("devDependencies", {}),
    }

    for name, specifier in declared.items():
        assert not str(specifier).startswith(("file:", "link:", "workspace:", "portal:")), (
            f"apps/consume-demo resolves {name!r} from {specifier!r}. A local-path "
            "dependency is a source dependency on whatever that path contains."
        )


# ── the credential ───────────────────────────────────────────────────

#: Every browser-side place a value can be written that outlives the tab, plus
#: the two places a credential most often leaks by accident.
_FORBIDDEN_STORAGE = (
    "localStorage",
    "sessionStorage",
    "indexedDB",
    "document.cookie",
    "window.name",
)


@pytest.mark.parametrize(
    "source", [p for p in _source_files() if not p.name.endswith((".test.ts", ".test.tsx"))], ids=_rel
)
def test_no_source_file_persists_anything(source: Path):
    """The token lives in React state for the life of the tab, and nowhere else.

    The check is on *any* persistence rather than on the token specifically,
    because a page that has a storage helper at all is one refactor away from
    putting the credential through it. There is nothing here worth persisting:
    the page holds one request and one receipt.

    Test files are exempt -- `App.test.tsx` reads `localStorage` and
    `sessionStorage` precisely to assert they stayed empty, and a guard that
    forbade naming them would forbid proving the thing it is guarding.
    """

    text = _code_only(source.read_text(encoding="utf-8"))
    for marker in _FORBIDDEN_STORAGE:
        assert marker not in text, (
            f"{_rel(source)} references {marker!r}. The playground holds a bearer "
            "token in memory for one tab; a credential that outlives the tab is a "
            "credential nobody remembers leaving behind."
        )


@pytest.mark.parametrize("source", _source_files(), ids=_rel)
def test_no_source_file_logs_to_the_console(source: Path):
    """A console line is a persistence layer with a scroll bar.

    Browser consoles are captured by extensions, by remote-debugging bridges and
    by screen recordings, and the value most likely to be logged while debugging
    a request is the request's own headers.
    """

    text = _code_only(source.read_text(encoding="utf-8"))
    assert not re.search(r"\bconsole\.(log|info|debug|warn|error|dir|table)\s*\(", text), (
        f"{_rel(source)} writes to the console. Nothing in this app needs to; "
        "the failure states are all rendered on the page, which is where a user "
        "can actually act on them."
    )


def test_the_environment_example_holds_a_url_and_no_credential():
    """Two variables, an address and an empty slot — and no value in either slot.

    A `VITE_` variable is inlined into the built bundle, so a credential in this
    file is a credential in `dist/`. `.env.example` is the file a reader copies,
    which is exactly why the wrong example is dangerous rather than merely
    untidy.

    `VITE_POLICY_SUBSCRIPTION_KEY` is *permitted to be named* here and required
    to be empty. Naming it is what documents the local-demonstration prefill and
    tells a reader which variable to set in their own untracked `.env.local`;
    filling it in is what would ship the credential. The two are different acts
    and only the second is refused.
    """

    example = (_APP / ".env.example").read_text(encoding="utf-8")

    declared = [
        line.split("=", 1)[0].strip()
        for line in example.splitlines()
        if line.strip() and not line.strip().startswith("#") and "=" in line
    ]
    assert declared == ["VITE_POLICY_API_BASE_URL", "VITE_POLICY_SUBSCRIPTION_KEY"], (
        f".env.example declares {declared}; the demo is configured by one base URL "
        "and an optional, empty local-demo key slot, and takes everything else "
        "from the page at run time."
    )

    values = {
        line.split("=", 1)[0].strip(): line.split("=", 1)[1].strip()
        for line in example.splitlines()
        if line.strip() and not line.strip().startswith("#") and "=" in line
    }
    assert values["VITE_POLICY_SUBSCRIPTION_KEY"] == "", (
        "apps/consume-demo/.env.example assigns a value to "
        f"VITE_POLICY_SUBSCRIPTION_KEY ({len(values['VITE_POLICY_SUBSCRIPTION_KEY'])} "
        "characters). It is inlined into the bundle and served to every visitor. "
        "The committed value must be empty; a real key belongs in an untracked "
        ".env.local."
    )
    assert "localhost" in values["VITE_POLICY_API_BASE_URL"], (
        "the committed base URL should be the repository-standard local address, "
        f"not {values['VITE_POLICY_API_BASE_URL']!r}"
    )


#: Anything that looks like a configured credential sitting in the tree.
#:
#: Deliberately shape-based rather than value-based: the guard cannot know the
#: operator's key, and a check that needed to know it would have to hold a copy.
#: What it can recognise is an assignment of a long opaque run to a variable
#: whose name says "key".
_KEY_ASSIGNMENT = re.compile(
    r"(?i)(subscription[_-]?key|api[_-]?key)\s*[=:]\s*['\"]?([A-Za-z0-9_\-+/]{20,})",
)

#: Substrings that make a long opaque-looking run obviously not a credential.
_NOT_A_KEY = ("your", "example", "placeholder", "the key your", "a-real", "demo-subscription-key")


@pytest.mark.parametrize("source", _source_files(), ids=_rel)
def test_no_source_file_carries_a_literal_looking_subscription_key(source: Path):
    """A credential belongs in `.env.local` and in React state, not in the tree.

    The demo *shows* the key on screen, which is a deliberate local-demo choice.
    It must still never be committed: a value on screen dies with the tab, and a
    value in a source file is in every clone, every fork and every diff for as
    long as the repository exists.
    """

    text = _code_only(source.read_text(encoding="utf-8"))
    for match in _KEY_ASSIGNMENT.finditer(text):
        candidate = match.group(2)
        if any(marker in candidate.lower() for marker in _NOT_A_KEY):
            continue
        raise AssertionError(
            f"{_rel(source)} assigns what looks like a real credential to "
            f"{match.group(1)!r}. Move it to an untracked .env.local; the "
            "committed default must be empty."
        )


def test_the_test_run_does_not_depend_on_a_developers_local_key():
    """The suite must pass on a machine that has never configured the demo.

    Vite loads `.env.local` for tests as well, so without this the assertions
    would render whoever's key happens to be on the machine — passing locally,
    failing in a clean checkout, and printing a credential into failure output
    on the way.
    """

    config = (_APP / "vitest.config.ts").read_text(encoding="utf-8")
    assert "'import.meta.env.VITE_POLICY_SUBSCRIPTION_KEY': '\"\"'" in config, (
        "vitest.config.ts should pin VITE_POLICY_SUBSCRIPTION_KEY empty via "
        "`define`, so the suite tests the committed default rather than the "
        "machine it runs on."
    )


def test_the_committed_configuration_carries_no_real_environment_file():
    """`.env` and its local variants are ignored, so a working local setup
    cannot be committed by habit.

    `.env.local` matters most here: it is where the demo's subscription key
    lives on a machine that has one, and it is the file most likely to be
    created by someone following the README.
    """

    ignored = [line.strip() for line in (_APP / ".gitignore").read_text(encoding="utf-8").splitlines()]

    for entry in (".env", ".env.local"):
        assert entry in ignored, (
            f"apps/consume-demo/.gitignore does not ignore {entry}; the first "
            "person to point the demo at a real environment will commit its "
            "address, and eventually its key"
        )

    assert ".env.example" not in ignored, (
        "apps/consume-demo/.gitignore ignores .env.example. That file is the "
        "committed template a reader copies and the only documentation of which "
        "variables exist; ignoring it makes the demo unconfigurable."
    )

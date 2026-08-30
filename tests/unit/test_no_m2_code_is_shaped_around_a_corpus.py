"""No part of the corpus-projection milestone is shaped around a corpus.

WHY THIS FILE EXISTS AND WHY IT READS THE SHIPPED CODE

Every defect this milestone repaired was found against one real corpus. That is
how it should be — a defect you cannot point at is a defect you cannot argue
about — but it is also exactly how a platform quietly stops being a platform. A
threshold tuned to a seventy-four-row schedule, a unit list written from the
questions that were asked, a branch that recognises a heading, a document id
left in a comparison: each would pass every test written against the corpus it
came from, and each would fail silently on the next customer's documents, in a
way nothing on screen would report.

So the rule is absolute and it is checked here rather than remembered: **the code
that ranks, indexes and projects may not name a subject, a document, an
organisation, a heading, an identifier or a vocabulary.** It works from the
record's own structure — a count against a threshold, a schema key, a rank
against another rank, a number against an interval — and from nothing else.

HOW IT CHECKS

By parsing the shipped modules, not by reading a description of them. The parse
is what makes the distinction the mandate draws actually enforceable:

  * **Documentation is not code.** A module docstring carrying the history of
    the decision that prompted a rule — including the corpus it was observed
    against — is provenance a maintainer needs, and erasing it would cost more
    than it protects. Docstrings and comments are therefore excluded, and only
    they. The mandate says a measured case may appear as a named regression
    fixture or a comment and never as the proof; this is the half of that which
    can be mechanically enforced.
  * **A model instruction is code.** A prompt is a string this platform sends,
    so every prompt constant is checked exactly like a comparison operand. It is
    an assignment, not a docstring, so the parse already treats it that way.
  * **Two tiers, two strengths.** The modules this milestone authored or
    rewrote are held to an absolute ban: no domain word anywhere in executable
    code, in any form. The modules it merely touched are held to the ban that
    matters — no domain word in an identifier, and none in a string that
    participates in *control flow or lookup*, which is the difference between a
    sentence a person reads and a branch a corpus can steer.

WHAT IT DOES NOT CLAIM

A guard cannot prove the absence of a corpus-shaped idea, only the absence of
its usual spellings and shapes. It is one of two halves. The other is that every
behaviour this milestone added is proved across four unrelated invented
domains — maritime, veterinary, procurement and a vocabulary that means nothing
at all — in `test_a_rule_is_found_on_its_own_terms.py` and
`test_the_corpus_is_indexed_in_one_language.py`, so no behaviour rests on a
single measured case. The last test here checks that that breadth is still
there, because a guard over the code is worth nothing if the tests shrink to one
corpus.
"""
from __future__ import annotations

import ast
import inspect
import os
import re

import pytest

os.environ.setdefault("DATABASE_URL", "******localhost:5433/test")
os.environ.setdefault("ALEMBIC_DATABASE_URL", "******localhost:5433/test")

from policy_platform.api import schemas  # noqa: E402
from policy_platform.api.routers import ai, policy_sets  # noqa: E402
from policy_platform.application import policy_case_decision  # noqa: E402
from policy_platform.contracts import case_decision  # noqa: E402
from policy_platform.domain import models  # noqa: E402
from policy_platform.infrastructure.assistants import ai_case_project  # noqa: E402
from policy_platform.infrastructure.projection import policy_rule_slice  # noqa: E402
from policy_platform.infrastructure.search import (  # noqa: E402
    english_projection,
    policy_index,
    search_client,
)

# ── the two tiers ────────────────────────────────────────────────────

#: Authored or substantially rewritten by this milestone. These decide what is
#: indexed, what is retrieved and in what order, so they carry the absolute ban.
AUTHORED = (
    english_projection,
    policy_index,
    search_client,
    policy_rule_slice,
    ai_case_project,
)

#: Touched by this milestone — a column, a field, a status code, a handler.
#: They carry pre-existing prose this milestone did not write and may not
#: rewrite, so the ban here is on what can *act*: identifiers, and strings that
#: participate in control flow or lookup.
TOUCHED = (
    policy_case_decision,
    case_decision,
    models,
    ai,
    policy_sets,
    schemas,
)

ALL_M2 = AUTHORED + TOUCHED

#: Subjects, documents, organisations and measured headings drawn from the
#: corpora this platform has actually been run against, plus the vocabulary of
#: the milestones' own worked examples and of this suite's own fixtures. Listed
#: *here*, in a test, which is the only place any of them belongs.
#:
#: Matched on word boundaries, not as substrings: an English sentence containing
#: "leaves" or "believe" is prose, and a guard that cannot tell those from a
#: branch on a leave policy is a guard nobody will keep.
DOMAIN_WORDS = (
    "ais",
    "hardware",
    "laptop",
    "leave",
    "leaves",
    "absence",
    "absences",
    "penalty",
    "penalties",
    "vacation",
    "violation",
    "violations",
    "lateness",
    "handbook",
    "employee",
    "payroll",
    "berth",
    "berthing",
    "pilotage",
    "veterinary",
    "procurement",
    "tender",
    "grelvin",
    "morticle",
    "morticles",
    "farnstable",
    "arabic",
    "english",
)

#: Magnitudes that appear in the incident record and nowhere else in a design:
#: the rows of the measured schedule, the rules and distinct texts of the
#: measured version, and the two character counts that were reported. A literal
#: equal to one of these in executable code is a branch fitted to what was
#: observed rather than a bound chosen for a reason.
MEASURED_MAGNITUDES = frozenset({74, 280, 229, 188_000, 229_389})

#: The only symbols allowed to carry the processing language's name. It *is*
#: named in code, once, deliberately: the whole design turns on there being one
#: language, and pretending it is unnamed would be a fiction. What must not exist
#: is a second one, or a name carrying a language invented anywhere other than
#: the boundary that declares it.
PROCESSING_LANGUAGE_SYMBOLS = frozenset(
    {
        "ENGLISH_PROJECTION_PROFILE",
        "EnglishProjectionReadiness",
        "EnglishProjectionError",
        "english_projection",
        "project_texts_to_english",
        "preservation_failure",
    }
)

#: The same allowance, for *identifiers only*. `NormalisedScenario.english` is
#: the boundary's own output field — the name of the thing it returns — and code
#: downstream reads it by that name. A **string** spelling the language would be
#: a value something could compare against, which is why this is not merged into
#: the set above: an attribute name and a literal are different risks.
PROCESSING_LANGUAGE_ATTRIBUTES = PROCESSING_LANGUAGE_SYMBOLS | {"english"}

#: Pre-existing platform vocabulary this milestone did not introduce, may not
#: rename, and does not read. Each entry is a stored column and its API field:
#: renaming one is a database migration and a breaking contract change, neither
#: of which belongs in a retrieval milestone.
#:
#: They are listed rather than tolerated silently, and the test below proves each
#: claim: that it appears only in the modules named here, and nowhere in any
#: module this milestone authored. If one ever turns up in the ranking or
#: indexing path, that is a new fact and this list will not hide it.
PRE_EXISTING_PLATFORM_NAMES = {
    "employee_name": "a stored column on the deterministic-evaluation record, and its API field",
    "employee_identifier": "the same record's optional external reference",
}

#: Keys of the canonical payload and of the index document. A collection of
#: these is a schema, not a vocabulary: each one names a field the record
#: actually has, and none of them is ever compared against a document's words.
SCHEMA_KEYS = frozenset(
    {
        "applies",
        "outcome",
        "name",
        "phrase",
        "unit",
        "role",
        "data_type",
        "source_phrase",
        "supersedes_rule_ids",
        "related_rule_ids",
        "rule_id",
        "evidence_refs",
        "effect",
        "exceptions",
        "limit_value",
        "limit_unit",
        "required_facts",
        "attributes",
        "fact_ref",
        "provision_key",
        "policy_version_id",
        "parent_document_id",
        "content_type",
        "document_version",
        "retrieval_text",
        "policy_id",
        "document_id",
        "id",
        "elevated_by_rule",
        "@search.score",
        "heading_path",
        "rules",
        "spans",
        "facts",
        "envelope",
    }
)


# ── reading a module the way this guard needs to ─────────────────────


def _docstring_ids(tree: ast.AST) -> set[int]:
    """Every string node that is a docstring, so they can be excluded and only they."""

    found: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            body = getattr(node, "body", [])
            if (
                body
                and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)
            ):
                found.add(id(body[0].value))
    return found


def _tree(module) -> ast.AST:
    return ast.parse(inspect.getsource(module))


def _identifiers(tree: ast.AST) -> set[str]:
    """Every name the module's code binds, reads or reaches through."""

    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            found.add(node.id)
        elif isinstance(node, ast.Attribute):
            found.add(node.attr)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            found.add(node.name)
        elif isinstance(node, ast.arg):
            found.add(node.arg)
        elif isinstance(node, ast.alias):
            found.add(node.name)
            if node.asname:
                found.add(node.asname)
        elif isinstance(node, ast.keyword) and node.arg:
            found.add(node.arg)
    return found


def _executable_strings(tree: ast.AST) -> list[str]:
    """Every string the module's code carries — prompts included, docstrings not."""

    docs = _docstring_ids(tree)
    return [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and id(node) not in docs
    ]


def _acting_strings(tree: ast.AST) -> list[str]:
    """Strings that steer behaviour rather than describe it.

    A string is *acting* when it is compared against something, used as a
    subscript or a dict key, listed in a collection, or handed to a lookup or a
    prefix test. Those are the positions from which a corpus can steer code. A
    string that only ends up in a sentence a person reads cannot.
    """

    docs = _docstring_ids(tree)
    found: list[str] = []

    def take(node: ast.AST) -> None:
        if (
            isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and id(node) not in docs
        ):
            found.append(node.value)

    for node in ast.walk(tree):
        if isinstance(node, ast.Compare):
            take(node.left)
            for comparator in node.comparators:
                take(comparator)
        elif isinstance(node, ast.Subscript):
            take(node.slice)
        elif isinstance(node, ast.Dict):
            for key in node.keys:
                if key is not None:
                    take(key)
        elif isinstance(node, (ast.Tuple, ast.List, ast.Set)):
            for element in node.elts:
                take(element)
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr in {
                "get",
                "setdefault",
                "pop",
                "startswith",
                "endswith",
                "count",
                "index",
                "split",
                "rsplit",
            }:
                for argument in node.args:
                    take(argument)
    return found


def _named_word(value: str, word: str) -> bool:
    """Whether `word` appears in `value` as a word rather than inside another."""

    return re.search(rf"(?<![a-z0-9]){re.escape(word)}(?![a-z0-9])", value.lower()) is not None


def _offences(values, *, allow=frozenset()) -> list[str]:
    out: list[str] = []
    for value in values:
        if value in allow:
            continue
        for word in DOMAIN_WORDS:
            if _named_word(value, word):
                out.append(f"{word!r} in {value[:80]!r}")
    return out


def _function(module, name: str) -> ast.AST:
    for node in ast.walk(_tree(module)):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return node
    raise AssertionError(f"{module.__name__} no longer defines {name}")


def _function_strings(module, name: str) -> list[str]:
    """Every string inside one function, its own docstring excluded.

    The exclusion has to be recomputed here: a function reached through the
    module tree carries its docstring like any other node, and a per-function
    check that forgot that would be reading the documentation it was written to
    ignore.
    """

    node = _function(module, name)
    docs = _docstring_ids(node)
    return [
        inner.value
        for inner in ast.walk(node)
        if isinstance(inner, ast.Constant)
        and isinstance(inner.value, str)
        and id(inner) not in docs
    ]


def _literal_type_strings(tree: ast.AST) -> set[int]:
    """String nodes inside a ``Literal[...]`` annotation.

    A `Literal` is a type: it declares the values a field may hold, in the same
    breath as declaring the field. That is a schema, not a vocabulary, and it is
    never compared against a document's words — so the word-list check steps over
    it rather than reading a state machine as a wordlist.
    """

    found: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Subscript):
            target = node.value
            name = getattr(target, "id", None) or getattr(target, "attr", None)
            if name == "Literal":
                for inner in ast.walk(node.slice):
                    if isinstance(inner, ast.Constant) and isinstance(inner.value, str):
                        found.add(id(inner))
    return found


# ── the ban, at both strengths ───────────────────────────────────────


@pytest.mark.parametrize("module", AUTHORED, ids=lambda m: m.__name__)
def test_no_authored_module_names_a_domain_anywhere_in_its_code(module):
    """The absolute form, over the modules that decide what is read.

    Every string the module carries and every name it binds. A prompt is a
    string, so a model instruction is covered by exactly this assertion — there
    is no separate rule for prompts because there is no separate mechanism.
    """

    tree = _tree(module)
    offences = _offences(
        _executable_strings(tree), allow=PROCESSING_LANGUAGE_SYMBOLS
    ) + _offences(_identifiers(tree), allow=PROCESSING_LANGUAGE_ATTRIBUTES)

    assert not offences, (
        f"{module.__name__} names a domain in executable code:\n  " + "\n  ".join(offences)
    )


@pytest.mark.parametrize("module", TOUCHED, ids=lambda m: m.__name__)
def test_no_touched_module_lets_a_domain_word_steer_behaviour(module):
    """The form that matters where this milestone did not write the prose.

    Identifiers, and strings in a position from which a corpus could steer the
    code. A domain word in a field description or an explanatory sentence is
    documentation; the same word in a comparison, a lookup key or a collection
    is a branch, and that is what is banned here.
    """

    tree = _tree(module)
    allowed_names = PROCESSING_LANGUAGE_ATTRIBUTES | set(PRE_EXISTING_PLATFORM_NAMES)
    offences = _offences(_acting_strings(tree), allow=PROCESSING_LANGUAGE_SYMBOLS) + _offences(
        _identifiers(tree), allow=allowed_names
    )

    assert not offences, (
        f"{module.__name__} lets a domain word steer behaviour:\n  " + "\n  ".join(offences)
    )


def test_the_pre_existing_platform_names_really_are_pre_existing():
    """Every entry in the allowance above is proved, not asserted.

    Two claims per entry: it is a stored field of a record this milestone does
    not touch, and it appears in **no** module this milestone authored. The
    second is the one that matters — an allowance that quietly started covering
    the ranking path would be exactly the hole this whole file exists to close.
    """

    assert PRE_EXISTING_PLATFORM_NAMES, "an empty allowance should be deleted, not kept"

    for module in AUTHORED:
        names = _identifiers(_tree(module)) | set(_executable_strings(_tree(module)))
        for allowed in PRE_EXISTING_PLATFORM_NAMES:
            assert allowed not in names, (
                f"{module.__name__} now uses {allowed!r}, which is platform vocabulary "
                "the retrieval path has no business reading"
            )

    # And each one is genuinely present where it is claimed to be, so the
    # allowance cannot outlive the thing it was written for.
    stored = _identifiers(_tree(models)) | _identifiers(_tree(schemas))
    for allowed, reason in PRE_EXISTING_PLATFORM_NAMES.items():
        assert allowed in stored, f"{allowed!r} is no longer {reason}; drop the allowance"


@pytest.mark.parametrize("module", ALL_M2, ids=lambda m: m.__name__)
def test_no_module_carries_a_project_key_or_a_record_identifier(module):
    """A digest in code is the corpus it was debugged against, pinned in place."""

    for value in _executable_strings(_tree(module)):
        stripped = value.replace("-", "").replace("_", "")
        assert not (
            len(stripped) >= 24
            and all(character in "0123456789abcdef" for character in stripped.lower())
        ), f"{module.__name__} carries what reads as a record identifier: {value!r}"


@pytest.mark.parametrize("module", AUTHORED, ids=lambda m: m.__name__)
def test_no_authored_module_branches_on_a_measured_magnitude(module):
    """A bound is chosen for a reason; a measurement is fitted to what was seen.

    Every number in these modules is a budget, a ceiling, a batch size or a
    published constant, and each is documented as such where it is declared.
    None of them is the size of anything that was observed.
    """

    for node in ast.walk(_tree(module)):
        if isinstance(node, ast.Constant) and isinstance(node.value, int):
            assert node.value not in MEASURED_MAGNITUDES, (
                f"{module.__name__} carries the measured magnitude {node.value}, "
                "which is a corpus fitted into code"
            )


@pytest.mark.parametrize("module", AUTHORED, ids=lambda m: m.__name__)
def test_no_authored_module_carries_a_word_list(module):
    """A collection of words is a vocabulary, and a vocabulary is a language.

    Every collection of strings in these modules must be one of two things: the
    keys of a schema the record actually has, or the values of constants this
    module itself declares. Anything else is a list of words somebody wrote down
    after reading a corpus — a stop-word list, a unit list, a list of connectives
    — and it is the single most common way a ranking stops being general.
    """

    tree = _tree(module)
    declared = {
        node.value.value
        for node in ast.walk(tree)
        if isinstance(node, (ast.Assign, ast.AnnAssign))
        and isinstance(getattr(node, "value", None), ast.Constant)
        and isinstance(node.value.value, str)
    }
    symbols = _identifiers(tree)
    allowed = SCHEMA_KEYS | declared | symbols | PROCESSING_LANGUAGE_SYMBOLS
    type_literals = _literal_type_strings(tree)

    for node in ast.walk(tree):
        if not isinstance(node, (ast.Tuple, ast.List, ast.Set)):
            continue
        if any(id(element) in type_literals for element in node.elts):
            continue
        elements = [
            element.value
            for element in node.elts
            if isinstance(element, ast.Constant) and isinstance(element.value, str)
        ]
        if len(elements) < 2 or len(elements) != len(node.elts):
            continue
        wordlike = [
            value
            for value in elements
            if value not in allowed and re.fullmatch(r"[a-z][a-z_]{2,}", value)
        ]
        assert not wordlike, (
            f"{module.__name__} carries a collection that reads as a vocabulary "
            f"rather than a schema: {wordlike}"
        )


# ── the three mechanisms, held to their stated shape ─────────────────


QUANTITY_FUNCTIONS = (
    "_atoms",
    "_numeric_value",
    "_unit_key",
    "units_match",
    "quantity_scalars",
    "quantity_ranges",
    "quantity_compatible",
    "_structured_quantity_text",
)


@pytest.mark.parametrize("name", QUANTITY_FUNCTIONS)
def test_numeric_matching_is_structural_and_names_no_unit(name: str):
    """A quantity is compared as a quantity: a value, an interval, and a token.

    Nothing in this path may know what a unit is *called*. It reads characters
    by Unicode category, takes the token next to a number as that number's unit
    whatever it says, and compares two units as two strings. The only strings it
    is allowed to carry are keys of the record's own schema — a carve-out's
    stored limit, a required fact's stored unit — never a word.
    """

    for value in _function_strings(policy_rule_slice, name):
        if value in SCHEMA_KEYS:
            continue
        assert not re.search(r"[A-Za-z]{3,}", value), (
            f"policy_rule_slice.{name} carries the word {value!r}; a unit or a "
            "connective named here is a corpus this ranking was tuned to"
        )


def test_numeric_matching_reads_characters_by_category_and_not_by_pattern():
    """`\\d` and `\\w` are claims about what a digit and a word look like.

    They are wrong in most of the scripts a governance corpus can be in, which is
    why the tokeniser stopped using them and why this path never started. The
    scan asks Unicode what each character is instead.
    """

    tree = _tree(policy_rule_slice)
    imported = {
        alias.name.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    } | {
        node.module.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module
    }
    assert "re" not in imported, "the ranking module reads text with a pattern again"
    assert "unicodedata" in imported

    atoms = ast.dump(_function(policy_rule_slice, "_atoms"))
    assert "isdigit" in atoms and "isalpha" in atoms and "category" in atoms


def test_rule_indexing_turns_on_a_count_against_a_threshold_and_nothing_else():
    """Which provisions get rule documents is a size question, not a subject one.

    The whole decision is `len(rules) > threshold`, and the only string it reads
    is the schema key that says a rule has an id. No heading, no key, no count
    fitted to a document that was measured.
    """

    node = _function(policy_index, "indexable_rules")

    compares = [inner for inner in ast.walk(node) if isinstance(inner, ast.Compare)]
    assert compares, "the threshold comparison is gone"
    assert any(
        isinstance(inner.comparators[0], ast.Name) and inner.comparators[0].id == "threshold"
        for inner in compares
    ), "the rule-document decision no longer turns on the declared threshold"

    for value in _function_strings(policy_index, "indexable_rules"):
        assert value in SCHEMA_KEYS, (
            f"indexable_rules reads {value!r}, which is not a schema key"
        )

    docs = _docstring_ids(node)
    for inner in ast.walk(node):
        if (
            isinstance(inner, ast.Constant)
            and isinstance(inner.value, int)
            and not isinstance(inner.value, bool)
            and id(inner) not in docs
        ):
            raise AssertionError(
                f"indexable_rules carries the literal {inner.value}; the threshold "
                "is a declared constant and a second number here is a second rule"
            )


RELATIONAL_FUNCTIONS = (
    (policy_rule_slice, "reciprocal_rank_scores"),
    (policy_rule_slice, "dense_ranks"),
    (policy_rule_slice, "fuse_rankings"),
    (policy_rule_slice, "evidence_diversity_quota"),
    (policy_rule_slice, "order_with_evidence_quota"),
    (policy_rule_slice, "_diverse_by_evidence"),
)


@pytest.mark.parametrize(
    "module,name", RELATIONAL_FUNCTIONS, ids=lambda value: getattr(value, "__name__", value)
)
def test_fusion_and_diversity_are_purely_relational(module, name: str):
    """These functions see positions, never text.

    Reciprocal-rank fusion combines rankings; the diversity reserve combines a
    ranking with a grouping. Both take integers and opaque group keys and return
    integers. A string anywhere in them would mean one of them had started
    reading the thing it is ordering, which is the point at which an ordering can
    be steered by what a document happens to say.
    """

    for value in _function_strings(module, name):
        raise AssertionError(f"{module.__name__}.{name} carries the string {value!r}")


def test_the_policy_and_rule_merge_reads_only_document_schema_keys():
    """The merge orders provisions by rank. What it reads is the schema, not the text."""

    for value in _function_strings(ai_case_project, "merge_policy_and_rule_hits"):
        assert value in SCHEMA_KEYS, (
            f"merge_policy_and_rule_hits reads {value!r}, which is not a "
            "document schema key"
        )


# ── and the other half: the tests are not one corpus either ──────────


def test_every_added_behaviour_is_proved_across_four_unrelated_domains():
    """A guard over the code is worth nothing if the proof shrinks to one corpus.

    The mandate is two-sided: the code names no domain, *and* what the code does
    is demonstrated on several that have nothing to do with one another. This
    reads the acceptance suite's own fixture set and fails if that breadth is
    lost — which is what would happen first if somebody repaired a failure by
    narrowing the fixtures instead of the code.

    A measured corpus may appear as a named regression fixture beside these. It
    may never be the only thing a behaviour is shown on, which is what having
    four unrelated ones here guarantees.
    """

    from tests.unit import test_a_rule_is_found_on_its_own_terms as ranking

    names = {corpus.name for corpus in ranking.CORPORA}
    assert len(names) >= 4, names

    for required in ("maritime", "veterinary", "procurement", "invented"):
        assert any(required in name for name in names), (
            f"the acceptance corpora no longer cover a {required} domain: {sorted(names)}"
        )

    # And one of them is written in a script the questions are not, so the
    # projection is exercised rather than assumed.
    assert any(not corpus.row.isascii() for corpus in ranking.CORPORA)

    # None of them is a corpus this platform was debugged against: every one is
    # invented for this suite, so no behaviour rests on a measured case.
    for corpus in ranking.CORPORA:
        blob = " ".join(
            [corpus.row, corpus.projected_row, corpus.subject, corpus.second_obligation]
        )
        for word in ("ais", "handbook", "laptop", "penalty", "penalties", "absence"):
            assert not _named_word(blob, word), (
                f"acceptance corpus {corpus.name} reuses a measured corpus' vocabulary"
            )

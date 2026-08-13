"""A capability that production cannot reach is not built, however well tested.

Three times in one week this codebase shipped a capability that was written,
covered by tests, and wired to nothing:

  * the structured document converter, with call sites in tests only, while
    the product flattened tables and lost column headers -- the exact failure
    the converter existed to prevent;
  * a repository write path with a migration, a model, an endpoint and a UI
    tab behind it, and no code anywhere that writes a row;
  * a package submission path whose refusal messages nothing can trigger.

Each passed its own tests. The suite was green. The product did not do the
thing. The missing invariant is not "is it tested" but *is it reachable*: a
public capability under `src/policy_platform` should have at least one caller
that is itself production code. Tests and scripts do not count -- a capability
exercised only from `tests/` is a capability the product never performs.

The analyser resolves method calls to a class where it honestly can, because
name matching alone cannot tell `EvaluationRepository.record` (called every
evaluation) from `ExtractionStageRepository.record` (called by nothing). Four
classes here define `record`. Where a receiver cannot be resolved the analyser
assumes the call *could* land anywhere, which loses findings rather than
inventing them: this guard is meant to be believed when it fires.
"""

from __future__ import annotations

import ast
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src" / "policy_platform"

#: Decorators that hand the callable to a framework which then calls it. The
#: shape is an attribute on an object -- `router.post`, `app.on_event`,
#: `event.listens_for`. A bare-name decorator such as `property` or
#: `staticmethod` is a descriptor, not a registration: whatever it wraps still
#: needs somebody to call it, so those are not treated as reachable here.
def _is_framework_registered(node: ast.AST) -> bool:
    for decorator in getattr(node, "decorator_list", []):
        target = decorator.func if isinstance(decorator, ast.Call) else decorator
        if isinstance(target, ast.Attribute):
            return True
    return False


#: Model surface rather than capability. A property, validator or serializer
#: is part of a data shape: it is reached by attribute access and by
#: serialization, neither of which a reference analyser can follow. Including
#: them buried the real findings under accessors, so the rule is drawn at
#: "something you invoke" rather than "something a model exposes".
_MODEL_SURFACE = frozenset(
    {
        "property",
        "cached_property",
        "computed_field",
        "field_validator",
        "model_validator",
        "field_serializer",
        "model_serializer",
        "validator",
        "root_validator",
        "abstractmethod",
        "overload",
    }
)


def _is_model_surface(node: ast.AST) -> bool:
    for decorator in getattr(node, "decorator_list", []):
        target = decorator.func if isinstance(decorator, ast.Call) else decorator
        name = target.id if isinstance(target, ast.Name) else getattr(target, "attr", "")
        if name in _MODEL_SURFACE:
            return True
    return False


@dataclass(frozen=True)
class Capability:
    """A public callable or class, and where it is declared."""

    module: str
    lineno: int
    qualname: str

    @property
    def key(self) -> str:
        return f"{self.module}::{self.qualname}"


@dataclass
class Reach:
    """What the analyser managed to look at, so blindness cannot pass as health."""

    modules: int = 0
    definitions: int = 0
    reachable: int = 0
    resolved_receivers: int = 0
    framework_registered: int = 0


def _definitions(tree: ast.Module) -> Iterable[tuple[str, ast.AST]]:
    """Public module-level callables and classes, plus public methods."""
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if not node.name.startswith("_"):
                yield node.name, node
            if isinstance(node, ast.ClassDef):
                for member in node.body:
                    if isinstance(member, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        if not member.name.startswith("_"):
                            yield f"{node.name}.{member.name}", member


def _class_bindings(tree: ast.Module, known: set[str]) -> dict[str, str]:
    """Variables whose class is stated outright, by construction or annotation.

    `repo = PolicySetRepository(session)` and `def f(repo: PolicySetRepository)`
    both say what `repo` is without any inference. That is enough to tell one
    class's `record` from another's, which is the whole difficulty.
    """
    binding: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Call):
            func = node.value.func
            if isinstance(func, ast.Name) and func.id in known:
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        binding[target.id] = func.id
        elif isinstance(node, (ast.AnnAssign, ast.arg)):
            annotation = getattr(node, "annotation", None)
            target = getattr(node, "target", None)
            name = target.id if isinstance(target, ast.Name) else getattr(node, "arg", None)
            if isinstance(annotation, ast.Name) and annotation.id in known and name:
                binding[name] = annotation.id
    return binding


def _collect_references(
    node: ast.AST,
    *,
    enclosing_class: str | None,
    binding: Mapping[str, str],
    known: set[str],
    names: set[str],
    strings: set[str],
    by_class: dict[str, set[str]],
    unresolved: set[str],
    reach: Reach,
) -> None:
    """Walk one module, carrying the class a node sits inside so `self` resolves.

    Imports are deliberately not references. Being re-exported from a package
    `__init__` is not being called, and treating it as a call is precisely how
    an unwired capability hides behind a tidy public API.
    """
    if isinstance(node, ast.Assign) and any(
        isinstance(t, ast.Name) and t.id == "__all__" for t in node.targets
    ):
        # Naming something in `__all__` re-exports it. String constants are
        # otherwise treated as references, to cover `getattr(obj, "name")`
        # dispatch -- but an export list is a declaration, not a call, and
        # counting it lets a tidy public API vouch for an unwired capability.
        return

    if isinstance(node, ast.ClassDef):
        enclosing_class = node.name
    elif isinstance(node, ast.Name):
        names.add(node.id)
    elif isinstance(node, ast.Constant) and isinstance(node.value, str):
        strings.add(node.value.strip())
    elif isinstance(node, ast.Attribute):
        receiver = node.value
        owner: str | None = None
        if isinstance(receiver, ast.Name):
            owner = enclosing_class if receiver.id == "self" else binding.get(receiver.id)
        elif isinstance(receiver, ast.Call) and isinstance(receiver.func, ast.Name):
            if receiver.func.id in known:
                owner = receiver.func.id
        if owner:
            by_class[owner].add(node.attr)
            reach.resolved_receivers += 1
        else:
            unresolved.add(node.attr)

    for child in ast.iter_child_nodes(node):
        _collect_references(
            child,
            enclosing_class=enclosing_class,
            binding=binding,
            known=known,
            names=names,
            strings=strings,
            by_class=by_class,
            unresolved=unresolved,
            reach=reach,
        )


def analyse(modules: Mapping[str, str]) -> tuple[list[Capability], Reach]:
    """Return public capabilities with no production caller, and what was seen.

    `modules` maps a module path to its source, so this runs identically over
    the repository and over a handful of synthetic modules in a test.
    """
    trees: dict[str, ast.Module] = {}
    for module, source in modules.items():
        try:
            trees[module] = ast.parse(source)
        except (SyntaxError, ValueError):
            continue

    known: set[str] = set()
    bases: dict[str, set[str]] = defaultdict(set)
    for tree in trees.values():
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                known.add(node.name)
                for base in node.bases:
                    if isinstance(base, ast.Name):
                        bases[node.name].add(base.id)

    reach = Reach(modules=len(trees))
    names: set[str] = set()
    strings: set[str] = set()
    by_class: dict[str, set[str]] = defaultdict(set)
    unresolved: set[str] = set()

    for tree in trees.values():
        _collect_references(
            tree,
            enclosing_class=None,
            binding=_class_bindings(tree, known),
            known=known,
            names=names,
            strings=strings,
            by_class=by_class,
            unresolved=unresolved,
            reach=reach,
        )

    def method_reached(owner: str, method: str) -> bool:
        if method in unresolved or method in strings:
            return True
        seen: set[str] = set()
        stack = [owner]
        while stack:  # a call on a subclass reaches the method it inherits
            current = stack.pop()
            if current in seen:
                continue
            seen.add(current)
            if method in by_class.get(current, ()):
                return True
            stack.extend(child for child, parents in bases.items() if current in parents)
        return False

    findings: list[Capability] = []
    for module, tree in trees.items():
        for qualname, node in _definitions(tree):
            reach.definitions += 1
            if _is_model_surface(node):
                reach.reachable += 1
                continue
            if _is_framework_registered(node):
                reach.framework_registered += 1
                reach.reachable += 1
                continue
            if "." in qualname:
                owner, method = qualname.split(".", 1)
                reached = method_reached(owner, method)
            else:
                reached = qualname in names or qualname in strings or qualname in unresolved
            if reached:
                reach.reachable += 1
            else:
                findings.append(Capability(module, node.lineno, qualname))

    return findings, reach


def _production_modules() -> dict[str, str]:
    """Production only. `tests/` and `scripts/` are not places a product runs."""
    return {
        str(path.relative_to(SRC)).replace("\\", "/"): path.read_text(encoding="utf-8")
        for path in sorted(SRC.rglob("*.py"))
    }


#: Capabilities already unreachable when this guard was written, each with the
#: reason it is tolerated for now. This is a quarantine, not an exemption list:
#: `test_every_quarantine_entry_is_earned` fails both when an entry names
#: something that no longer exists and when it names something that has since
#: been wired up. So the list can only shrink, and it tells you when it should.
#:
#: Nothing here is endorsed. Deciding which of these to connect, which to
#: delete and which are legitimately tooling-only is a product decision.
_QUARANTINE: dict[str, str] = {
    # --- Built, tested, never connected. The defect this guard exists for. ---
    "infrastructure/docling/pipeline.py::run_extraction": "structured converter; test call sites only",
    "infrastructure/docling/handoff.py::submit_package": "package submission path; no production caller",
    "infrastructure/docling/handoff.py::preview_handoff": "same path, preview half",
    "infrastructure/persistence/extraction_stage_repository.py::ExtractionStageRepository.record": "stage write; table has migration, model, endpoint and UI tab, and no writer",
    "infrastructure/persistence/extraction_stage_repository.py::ExtractionStageRepository.latest_status": "same repository",
    "infrastructure/persistence/extraction_stage_repository.py::ExtractionStageRepository.next_attempt": "same repository",
    "infrastructure/persistence/extraction_stage_repository.py::ExtractionStageRepository.completed_stage_names": "same repository",
    "infrastructure/ingestion/document_extraction.py::extract_clauses": "reached from scripts only; owned by another workstream",
    "domain/models.py::OutboxMessage": "outbox table and ORM model; nothing constructs a row -- same shape as the stage repository",
    "infrastructure/docling/dependency_provenance.py::require_dependency_integrity": "its own docstring calls it 'the raising variant used by gates'; no gate calls it",
    "infrastructure/docling/graph_runtime.py::build_runtime": "graph runtime construction; test call sites only",
    "infrastructure/docling/graph_runtime.py::DoclingGraphRuntime.pipeline_config": "same runtime",
    # --- Deliberate tooling. Reachable from tooling is the intended design. ---
    "infrastructure/docling/shadow_comparison.py::compare": "shadow comparator, intended to run from tooling only",
    "infrastructure/docling/shadow_comparison.py::format_report": "same comparator",
    # --- Search projection and client: whole surface uncalled in production. ---
    "infrastructure/search/projection.py::build_runtime_document": "search projection surface",
    "infrastructure/search/projection.py::build_review_document": "search projection surface",
    "infrastructure/search/projection.py::verify_projection": "search projection surface",
    "infrastructure/search/projection.py::runtime_query_filter": "search projection surface",
    "infrastructure/search/projection.py::ProjectionVerification.failure_summary": "search projection surface",
    "infrastructure/search/search_client.py::AzureSearchClient.find_ids_by_filter": "search client surface",
    "infrastructure/search/search_client.py::AzureSearchClient.delete_documents": "search client surface",
    # --- Repository operations with no production call site. ---
    "infrastructure/persistence/repositories/policy_sets.py::PolicySetRepository.create": "repository operation, no caller",
    "infrastructure/persistence/repositories/policy_sets.py::PolicySetRepository.list_all": "repository operation, no caller",
    "infrastructure/persistence/repositories/policy_sets.py::PolicySetRepository.update_metadata": "repository operation, no caller",
    "infrastructure/persistence/repositories/policy_sets.py::PolicySetRepository.mark_reviewed": "repository operation, no caller",
    "infrastructure/persistence/repositories/documents.py::ClauseRepository.has_clauses": "repository operation, no caller",
    "infrastructure/persistence/repositories/documents.py::ClauseRepository.delete_by_document_version": "repository operation, scripts only",
    "infrastructure/persistence/repositories/candidates.py::ExtractionRunRepository.get_by_id": "repository operation, no caller",
    "infrastructure/persistence/repositories/policy_tests.py::PolicyTestRunRepository.get_latest_by_test": "repository operation, no caller",
    "infrastructure/persistence/repositories/versions.py::ApprovedPolicyVersionRepository.insert_version": "repository operation, no caller",
    # --- Analysis helpers with no production call site. ---
    "infrastructure/quality/logic_faithfulness.py::judge_logic": "quality judge, test call sites only",
    "infrastructure/extraction/policy_parties.py::is_judgement_bounded": "helper, test call sites only",
    "infrastructure/ingestion/source_structure.py::detect_references": "helper, test call sites only",
    "infrastructure/ingestion/source_structure.py::push_heading": "helper, test call sites only",
    # --- Contract shapes and helpers nothing in production constructs or calls. ---
    "contracts/canonical_document.py::SpanReference": "contract type, unconstructed in production",
    "contracts/canonical_document.py::CanonicalDocument.element_by_id": "contract helper, no caller",
    "contracts/policy.py::PrincipalContext": "contract type, unconstructed in production",
    "contracts/policy.py::PrincipalContext.to_facts": "contract helper, no caller",
    "contracts/policy_context.py::SourceElement": "contract type, unconstructed in production",
    "contracts/policy_context.py::PolicyContextUnit": "contract type, unconstructed in production",
    "contracts/policy_context.py::CoverageManifest": "contract type, unconstructed in production",
    "contracts/policy_context.py::CoverageManifest.unresolved_element_ids": "contract helper, no caller",
    "contracts/relationships.py::PolicyRelationshipGraph": "contract type, unconstructed in production",
    "contracts/relationships.py::PolicyRelationshipGraph.for_rule": "contract helper, no caller",
    "contracts/relationships.py::PolicyRelationshipGraph.by_type": "contract helper, no caller",
    "contracts/evidence_resolution.py::EvidenceResolution.by_role": "contract helper, no caller",
    "contracts/extraction_package.py::PolicyExtractionPackage.evidence_for": "contract helper, no caller",
    "contracts/extraction_package.py::PolicyExtractionPackage.unsupported_projections": "contract helper, no caller",
    "contracts/element_identity.py::is_valid_element_id": "contract helper, no caller",
    "contracts/element_identity.py::is_legacy_element_id": "contract helper, no caller",
    "contracts/graph_run.py::evaluate_coverage_gates": "contract helper, no caller",
    "contracts/policy_document_graph.py::validate_candidates": "contract helper, no caller",
    "contracts/policy_document_graph.py::edge_labels": "contract helper, no caller",
    "contracts/reading_plan.py::find_cross_references": "contract helper, no caller",
}


# --------------------------------------------------------------------------
# The analyser, proved on synthetic modules rather than on this repository.
# --------------------------------------------------------------------------


def test_an_unwired_capability_is_found():
    """The shape of the defect: defined in production, called only by a test."""

    findings, _ = analyse(
        {
            "thing.py": "def perform():\n    return 1\n",
            "caller.py": "from thing import perform\n",  # imported, never called
        }
    )
    assert [f.key for f in findings] == ["thing.py::perform"]


def test_a_capability_with_a_production_caller_is_not_found():
    findings, _ = analyse(
        {
            "thing.py": "def perform():\n    return 1\n",
            "caller.py": "from thing import perform\n\ndef go():\n    return perform()\n",
        }
    )
    assert [f.key for f in findings] == ["caller.py::go"], [f.key for f in findings]


def test_two_classes_sharing_a_method_name_are_told_apart():
    """The reason this analyser resolves receivers at all.

    Both classes declare `record`. One is constructed and called, the other is
    not. A guard that matched on the bare name would clear both.
    """

    findings, _ = analyse(
        {
            "repos.py": (
                "class Used:\n"
                "    def record(self, x):\n"
                "        return x\n"
                "\n"
                "class Unused:\n"
                "    def record(self, x):\n"
                "        return x\n"
            ),
            "caller.py": (
                "from repos import Used\n"
                "\n"
                "def go(session):\n"
                "    repo = Used(session)\n"
                "    return repo.record(1)\n"
            ),
        }
    )
    keys = {f.key for f in findings}
    assert "repos.py::Unused.record" in keys
    assert "repos.py::Used.record" not in keys


def test_a_framework_registered_handler_is_not_found():
    """Nothing calls a route by name; the router does, on a request."""

    findings, _ = analyse(
        {
            "routes.py": (
                "router = object()\n"
                "\n"
                "@router.get('/x')\n"
                "def handler():\n"
                "    return 1\n"
            )
        }
    )
    assert [f.key for f in findings] == []


def test_a_descriptor_is_not_mistaken_for_a_registration():
    """`@property` wraps; it does not register. What it wraps is model surface,
    so it is skipped for that reason -- but a `@staticmethod` still needs a
    caller, and must not be waved through just for carrying a decorator."""

    findings, _ = analyse(
        {
            "shapes.py": (
                "class Shape:\n"
                "    @property\n"
                "    def size(self):\n"
                "        return 1\n"
                "\n"
                "    @staticmethod\n"
                "    def helper():\n"
                "        return 1\n"
            ),
            "caller.py": "from shapes import Shape\n\ndef go():\n    return Shape()\n",
        }
    )
    keys = {f.key for f in findings}
    assert "shapes.py::Shape.helper" in keys, "a staticmethod still needs a caller"
    assert "shapes.py::Shape.size" not in keys, "a property is model surface"


def test_an_inherited_method_is_reached_through_its_subclass():
    findings, _ = analyse(
        {
            "base.py": (
                "class Base:\n"
                "    def perform(self):\n"
                "        return 1\n"
                "\n"
                "class Child(Base):\n"
                "    pass\n"
            ),
            "caller.py": (
                "from base import Child\n"
                "\n"
                "def go():\n"
                "    return Child().perform()\n"
            ),
        }
    )
    assert "base.py::Base.perform" not in {f.key for f in findings}


def test_being_re_exported_is_not_being_called():
    """The tidy public API that hides an unwired capability."""

    findings, _ = analyse(
        {
            "thing.py": "def perform():\n    return 1\n",
            "__init__.py": "from thing import perform\n\n__all__ = ['perform']\n",
        }
    )
    assert "thing.py::perform" in {f.key for f in findings}


# --------------------------------------------------------------------------
# The repository.
# --------------------------------------------------------------------------


def test_the_analyser_can_see():
    """A guard that has gone blind finds nothing and looks like good news.

    These floors are far below what the repository actually contains. They
    fail if the scan stops finding modules, stops examining definitions, stops
    resolving receivers, or stops recognising framework registration -- each of
    which would quietly empty the result.
    """

    modules = _production_modules()
    assert len(modules) > 50, f"only {len(modules)} production modules found"

    _, reach = analyse(modules)
    assert reach.definitions > 300, f"only {reach.definitions} definitions examined"
    assert reach.reachable > 200, f"only {reach.reachable} judged reachable"
    assert reach.resolved_receivers > 100, f"only {reach.resolved_receivers} receivers resolved"
    assert reach.framework_registered > 20, (
        f"only {reach.framework_registered} framework registrations recognised; "
        "if this collapses, every route handler becomes a false finding"
    )


def test_every_quarantine_entry_is_earned():
    """Same rule as the framing guard: an entry that protects nothing goes.

    An entry stops being earned for three reasons: the capability no longer
    exists, somebody wired it up, or the analyser stopped detecting it. The
    second is the good outcome, and this is how the quarantine notices and
    shrinks. The third means this guard has regressed -- which makes these
    entries a standing regression bar, since the three capabilities that
    prompted the guard are among them and must keep being found.
    """

    findings, _ = analyse(_production_modules())
    unreachable = {f.key for f in findings}
    declared = set(_QUARANTINE)

    connected = sorted(declared - unreachable)
    assert not connected, (
        "quarantined capabilities that are now reachable (or gone) -- "
        "remove these entries:\n  " + "\n  ".join(connected)
    )


def test_no_unreachable_capability_outside_quarantine():
    """A capability production cannot reach is not delivered, only written."""

    findings, reach = analyse(_production_modules())
    assert reach.definitions > 300, (
        f"only {reach.definitions} definitions examined; an analyser that reads "
        "nothing reports no offenders and passes on silence"
    )

    offenders = sorted(
        f"{f.module}:{f.lineno} {f.qualname}"
        for f in findings
        if f.key not in _QUARANTINE
    )
    assert not offenders, (
        "public capabilities with no production caller:\n  "
        + "\n  ".join(offenders)
        + "\n\nEither wire it to something the product runs, or delete it. "
        "If it is deliberately reachable from tooling only, add it to "
        "_QUARANTINE with the reason."
    )

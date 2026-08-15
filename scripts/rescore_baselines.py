"""Re-score existing policy sets with today's detector suite, changing nothing.

Comparing a fresh run scored with today's detectors against numbers recorded
days ago with older detectors measures two things at once — the system changing
and the instrument changing — and cannot separate them. This runs the *current*
detectors over records that already exist, so both sides of a comparison are
measured with the same instrument.

Read-only by construction, not by intention:

* Records are loaded with `psql -c "select ..."`. There is no session, no ORM
  and no transaction that could write.
* The detector suite is `_deterministic_findings`, the same pure function the
  production path calls. The two functions wrapping it
  (`evaluate_policy_set_quality`, `evaluate_candidate_quality`) are the only
  ones that commit, and both guard the commit behind `record_run`.
* `--verify-readonly` fingerprints every table before and after and fails if
  anything moved.

No model is called, so a re-score is reproducible. The recorded runs are not:
six AI-reviewed runs over the identical 273 records produced 30 to 34 findings.

The record filter matches production exactly — current generation only
(`superseded_at is null`), review status `candidate` or `approved` — because a
count taken with a different filter is not a re-score of the same thing.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from policy_platform.contracts.policy import CanonicalRule  # noqa: E402
from policy_platform.infrastructure.quality import ai_quality  # noqa: E402
from policy_platform.infrastructure.quality.ai_quality import (  # noqa: E402
    _deterministic_findings,
)

DB = ("-U", "policy_admin", "-d", "policy_platform_advtool")

#: Mirrors `CandidateRuleRepository.list_by_policy_set` defaults.
RULES_SQL = """
select c.payload_json
from candidate_rules c
join policy_sets p on p.id = c.policy_set_id
where p.key = '{key}'
  and c.superseded_at is null
  and c.review_status in ('candidate', 'approved')
"""

#: Clauses belonging to the document versions this policy set was extracted
#: from. Coverage is measured against these because `evidence_references` is
#: empty for all four sets — that table is populated on publish, and none of
#: them has an approved version, so a SQL-side coverage measure reads 0.0%
#: for every set regardless of what the records actually cite.
CLAUSES_SQL = """
select count(*), count(distinct page) from clauses
where document_version_id in (
  select distinct x.document_version_id
  from extraction_runs x
  join candidate_rules c on c.extraction_run_id = x.id
  join policy_sets p on p.id = c.policy_set_id
  where p.key = '{key}' and c.superseded_at is null)
"""

#: What a recorded run captured, for the side-by-side.
RUNS_SQL = """
select json_agg(x) from (
  select q.scope, q.rule_count, q.methodology_version, q.ai_review_used,
         q.high_count, q.medium_count, q.low_count,
         jsonb_array_length(q.findings_json) as findings,
         q.run_at::text, q.findings_json
  from quality_runs q join policy_sets p on p.id = q.policy_set_id
  where p.key = '{key}' order by q.run_at
) x
"""

FINGERPRINT_SQL = """
select json_agg(x) from (
  select 'candidate_rules' as t, count(*) c, max(updated_at)::text m from candidate_rules
  union all select 'quality_runs', count(*), max(updated_at)::text from quality_runs
  union all select 'policy_sets', count(*), max(updated_at)::text from policy_sets
  union all select 'extraction_runs', count(*), max(updated_at)::text from extraction_runs
  union all select 'candidate_generations', count(*), max(superseded_at)::text from candidate_rules
) x
"""


def psql(sql: str) -> str:
    out = subprocess.run(
        ["docker", "exec", "policy-postgres", "psql", *DB, "-t", "-A", "-c", sql],
        capture_output=True, text=True, encoding="utf-8", check=True,
    )
    return out.stdout


def load_rules(key: str) -> tuple[list[CanonicalRule], list[str]]:
    rules, bad = [], []
    for line in psql(RULES_SQL.format(key=key)).splitlines():
        if not line.strip():
            continue
        try:
            rules.append(CanonicalRule.model_validate(json.loads(line)))
        except Exception as exc:  # noqa: BLE001 - counted, not hidden
            bad.append(str(exc)[:120])
    return rules, bad


def recorded_runs(key: str) -> list[dict]:
    raw = psql(RUNS_SQL.format(key=key)).strip()
    return json.loads(raw) if raw and raw != "" else []


def fingerprint() -> str:
    return psql(FINGERPRINT_SQL).strip()


def instrument_id() -> str:
    """What scored these records, in terms that can be checked.

    The commit is a locator, not an identity: an uncommitted edit to a detector
    leaves the hash unchanged while changing what the suite finds, so two runs
    could claim the same instrument and not share one. That is the exact defect
    the methodology version exists to prevent, so the harness reports the
    derived version too and a dirty tree is stated rather than hidden.
    """
    out = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True
    )
    commit = out.stdout.strip() or "unknown"

    dirty = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=no"],
        capture_output=True,
        text=True,
    )
    if dirty.stdout.strip():
        commit += " (tree dirty)"

    return f"{commit}, method {ai_quality.QUALITY_METHODOLOGY_VERSION}"


def clause_totals(key: str) -> tuple[int, int]:
    raw = psql(CLAUSES_SQL.format(key=key)).strip()
    if not raw:
        return 0, 0
    total, pages = raw.split("|")
    return int(total), int(pages)


def blank_titles(rules: list[CanonicalRule]) -> list[CanonicalRule]:
    """Return copies with the title removed, to isolate a known confound.

    `policy_faithfulness` builds its search surface from
    `[rule.title, rule.effect.action, ...]`. The title is *composed* by the
    formulator, not extracted from the source, so a better title can suppress a
    finding by supplying the very term the detector is looking for.

    That matters here because the fresh runs get corrected titles by
    construction while the baselines carry stale ones, so any fresh-versus-
    baseline faithfulness number is contaminated in the direction that flatters
    us. Blanking on *both* sides removes the field from the comparison
    entirely: the absolute numbers then match nothing previously reported, but
    the difference between the two sides is attributable again.

    Copies, not mutation — the loaded records are also used for the unblanked
    scoring in the same process, and an in-place edit would silently poison it.
    """
    return [r.model_copy(update={"title": ""}) for r in rules]


def score(key: str, *, blank_title: bool = False) -> dict:
    rules, bad = load_rules(key)
    if blank_title:
        rules = blank_titles(rules)
    findings = _deterministic_findings(rules)

    by_cat = Counter(f["category"] for f in findings)
    by_sev = Counter(f["severity"] for f in findings)
    cat_sev = Counter((f["category"], f["severity"]) for f in findings)
    routes = Counter(r.evaluation_mode.value for r in rules)

    # Coverage from the records themselves. Every record carries its own
    # evidence, so this needs no join and stays correct for unpublished sets.
    cited_clauses = {e.clause_id for r in rules for e in r.evidence if e.clause_id}
    cited_pages = {e.page for r in rules for e in r.evidence if e.page is not None}
    no_evidence = sum(1 for r in rules if not r.evidence)
    total_clauses, total_pages = clause_totals(key)

    return {
        "key": key,
        "rules": len(rules),
        "unparseable": bad,
        "routes": dict(routes),
        "machine_executable": sum(1 for r in rules if r.machine_executable),
        "findings": len(findings),
        "by_severity": dict(by_sev),
        "by_category": dict(by_cat.most_common()),
        "cat_sev": {f"{c}/{s}": n for (c, s), n in sorted(cat_sev.items())},
        "affected_rules": len({r for f in findings for r in f.get("affected_rule_ids", [])}),
        "coverage": {
            "clauses_total": total_clauses,
            "clauses_cited": len(cited_clauses),
            "pages_total": total_pages,
            "pages_cited": len(cited_pages),
            "records_without_evidence": no_evidence,
        },
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("keys", nargs="*", help="policy set keys; default all")
    ap.add_argument("--verify-readonly", action="store_true")
    ap.add_argument(
        "--blank-titles",
        action="store_true",
        help="score with rule.title removed, to isolate the composed-title confound",
    )
    ap.add_argument("--json", type=str, default="")
    args = ap.parse_args()

    keys = args.keys or [
        k.strip() for k in psql("select key from policy_sets order by created_at").splitlines()
        if k.strip()
    ]

    before = fingerprint() if args.verify_readonly else None

    print(f"instrument: detector suite at commit {instrument_id()}")
    print(f"mode      : deterministic only (no model call), record_run disabled")
    if args.blank_titles:
        print("titles    : BLANKED — absolute numbers are not comparable to any")
        print("            previously reported figure; only blanked-vs-blanked is\n")
    else:
        print("")

    results = []
    for key in keys:
        r = score(key, blank_title=args.blank_titles)
        results.append(r)
        print("=" * 70)
        print(f"{key}")
        print("=" * 70)
        print(f"  records scored     : {r['rules']}")
        if r["unparseable"]:
            print(f"  UNPARSEABLE        : {len(r['unparseable'])}")
        print(f"  route              : {r['routes']}")
        print(f"  machine_executable : {r['machine_executable']}")
        print(f"  findings (total)   : {r['findings']}   {r['by_severity']}")
        print(f"  rules implicated   : {r['affected_rules']}")
        cov = r["coverage"]
        print(
            f"  coverage           : {cov['clauses_cited']}/{cov['clauses_total']} clauses cited"
            f", {cov['pages_cited']}/{cov['pages_total']} pages"
            f", {cov['records_without_evidence']} records with no evidence"
        )
        print("  by category:")
        for cat, n in r["by_category"].items():
            print(f"      {n:>4}  {cat}")

        runs = recorded_runs(key)
        if not runs:
            print("\n  recorded runs      : none — no prior number exists for this set")
        else:
            print(f"\n  recorded runs      : {len(runs)}")
            print("      when                  ai   rules  findings  hi/med/lo  meth")
            for q in runs:
                print(
                    f"      {q['run_at'][:19]}  {'Y' if q['ai_review_used'] else 'N'}"
                    f"    {q['rule_count']:>4}   {q['findings']:>6}"
                    f"    {q['high_count']}/{q['medium_count']}/{q['low_count']}"
                    f"     v{q['methodology_version']}"
                )
            det = [q for q in runs if not q["ai_review_used"]]
            if det:
                d = det[-1]
                print(
                    f"\n  comparable baseline: the {d['run_at'][:19]} run used no model."
                    f"\n      then : {d['findings']} findings ({d['high_count']}/{d['medium_count']}/{d['low_count']})"
                    f"\n      now  : {r['findings']} findings "
                    f"({r['by_severity'].get('high',0)}/{r['by_severity'].get('medium',0)}/{r['by_severity'].get('low',0)})"
                    f"\n      delta: {r['findings'] - d['findings']:+d}  <- instrument change only;"
                    " the records did not move"
                )
                then_cat = Counter(f["category"] for f in d["findings_json"])
                now_cat = Counter(f["category"] for f in _deterministic_findings(load_rules(key)[0]))
                moved = {c for c in set(then_cat) | set(now_cat) if then_cat[c] != now_cat[c]}
                if moved:
                    print("      per detector (then -> now):")
                    for c in sorted(moved):
                        print(f"        {then_cat[c]:>4} -> {now_cat[c]:<4}  {c}")
        print()

    if args.verify_readonly:
        after = fingerprint()
        print("=" * 70)
        if before == after:
            print("READ-ONLY VERIFIED: database fingerprint identical before and after.")
            print(f"  {before}")
        else:
            print("WRITE DETECTED — scoring path is not read-only:")
            print(f"  before: {before}\n  after : {after}")
            return 1

    if args.json:
        Path(args.json).write_text(json.dumps(results, indent=2), encoding="utf-8")
        print(f"\nwrote {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

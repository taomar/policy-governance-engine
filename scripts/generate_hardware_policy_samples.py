"""One-off generator for the hardware-provisioning-policy sample rule sets.

Produces samples/policies/hardware-policy-v3.2-import.json and
hardware-policy-v3.3-import.json from the real source documents in
samples/source-documents/ (Workplace Hardware Provisioning Policy, POL-HW-001).
The only substantive rule change between the two versions is the contractor
entitlement threshold (20 working days -> 10 working days), matching the
document's own amendment history table. This script is not part of the
runtime application; it's a one-time authoring aid, kept for traceability.
"""
import json
from pathlib import Path

AUTHORITY = {"level": "corporate", "owner": "digital-workplace", "rank": 10}
ADJUSTMENT_AUTHORITY = {"level": "corporate-hr", "owner": "occupational-health", "rank": 20}
SECURITY_AUTHORITY = {"level": "corporate-security", "owner": "information-security", "rank": 30}
SCOPE = {"jurisdictions": ["*"], "organizational_units": ["*"], "personas": ["*"], "processes": ["hardware_provisioning"]}


def rule(rule_id, title, description, rule_type, condition, effect_type, effect_action,
         required_facts, authority=None, exceptions=None, priority=0):
    return {
        "policy_set_id": "hardware-provisioning-policy",
        "policy_version_id": "vX",
        "rule_id": rule_id,
        "rule_revision": 1,
        "title": title,
        "description": description,
        "rule_type": rule_type,
        "authority": authority or AUTHORITY,
        "scope": SCOPE,
        "condition": condition,
        "effect": {"type": effect_type, "action": effect_action},
        "required_facts": required_facts,
        "exceptions": exceptions or [],
        "priority": priority,
        "effective_from": "2026-04-01",
    }


def fact(f, op, v):
    return {"type": "factComparison", "fact": f, "operator": op, "value": v}


def build_rules(contractor_threshold_days: int):
    return [
        rule(
            "RULE-HW-001", "Self-service approval tier (<=150)",
            "Requests at or below $150 require no approval and are fulfilled as self-service (Table 7.1).",
            "approval_requirement", fact("request_value_usd", "lessThanOrEqual", 150),
            "allow", "auto_approve",
            [{"name": "request_value_usd", "data_type": "number", "required": True}],
        ),
        rule(
            "RULE-HW-002", "Line manager approval tier (151-600)",
            "Requests from $151 to $600 require line manager approval (Table 7.1).",
            "approval_requirement",
            {"type": "all", "all": [fact("request_value_usd", "greaterThan", 150), fact("request_value_usd", "lessThanOrEqual", 600)]},
            "require_action", "line_manager_approval",
            [{"name": "request_value_usd", "data_type": "number", "required": True}],
        ),
        rule(
            "RULE-HW-003", "Manager + Asset Management tier (601-2,500)",
            "Requests from $601 to $2,500 require line manager and Asset Management approval (Table 7.1).",
            "approval_requirement",
            {"type": "all", "all": [fact("request_value_usd", "greaterThan", 600), fact("request_value_usd", "lessThanOrEqual", 2500)]},
            "require_action", "manager_and_asset_management_approval",
            [{"name": "request_value_usd", "data_type": "number", "required": True}],
        ),
        rule(
            "RULE-HW-004", "Manager + Asset Management + Finance tier (2,501-10,000)",
            "Requests from $2,501 to $10,000 require line manager, Asset Management, and Finance Business Partner approval (Table 7.1).",
            "approval_requirement",
            {"type": "all", "all": [fact("request_value_usd", "greaterThan", 2500), fact("request_value_usd", "lessThanOrEqual", 10000)]},
            "require_action", "manager_asset_finance_approval",
            [{"name": "request_value_usd", "data_type": "number", "required": True}],
        ),
        rule(
            "RULE-HW-005", "Director approval tier (>10,000)",
            "Requests above $10,000 additionally require Director, Digital Workplace approval (Table 7.1).",
            "approval_requirement", fact("request_value_usd", "greaterThan", 10000),
            "require_action", "manager_asset_finance_director_approval",
            [{"name": "request_value_usd", "data_type": "number", "required": True}],
        ),
        rule(
            "RULE-HW-006", "Third device refused",
            "A request for a third computing device held at one time is refused unless raised as an exception (2.2).",
            "prohibition", fact("devices_held_count", "greaterThanOrEqual", 3),
            "deny", "refuse_request",
            [{"name": "devices_held_count", "data_type": "number", "required": True}],
        ),
        rule(
            "RULE-HW-007", "Contractor permanent-allocation entitlement",
            f"Contractors engaged for {contractor_threshold_days} working days or fewer are not entitled to a permanent allocation and are served from loan stock only (1.1).",
            "eligibility",
            {"type": "all", "all": [fact("is_contractor", "equals", True), fact("engagement_days", "lessThanOrEqual", contractor_threshold_days)]},
            "deny", "deny_permanent_allocation_use_loan_stock",
            [
                {"name": "is_contractor", "data_type": "boolean", "required": True},
                {"name": "engagement_days", "data_type": "number", "required": True},
            ],
        ),
        rule(
            "RULE-HW-008", "Self-approval prohibited",
            "No colleague may approve their own request or a request from a person to whom they report; approval passes to the next level (7.3).",
            "prohibition",
            {"type": "any", "any": [fact("approver_is_requester", "equals", True), fact("approver_reports_to_requester", "equals", True)]},
            "deny", "escalate_to_next_management_level",
            [
                {"name": "approver_is_requester", "data_type": "boolean", "required": True},
                {"name": "approver_reports_to_requester", "data_type": "boolean", "required": True},
            ],
        ),
        rule(
            "RULE-HW-009", "Workplace adjustment priority override",
            "Equipment required as a workplace adjustment bypasses the financial thresholds, entitlement limits, and refresh interval, and is approved by Asset Management alone (9.1, Appendix A.3).",
            "approval_requirement", fact("is_workplace_adjustment", "equals", True),
            "allow", "asset_management_priority_approval",
            [{"name": "is_workplace_adjustment", "data_type": "boolean", "required": True}],
            authority=ADJUSTMENT_AUTHORITY,
            priority=10,
        ),
        rule(
            "RULE-HW-010", "Security suspension overrides all issuance",
            "A device that has not checked in for 30+ days is suspended from network access; no further equipment is issued to that colleague until resolved, overriding every other provision including 9.1 (16.2, Appendix A.4).",
            "prohibition", fact("device_suspended_for_noncompliance", "equals", True),
            "deny", "block_all_issuance",
            [{"name": "device_suspended_for_noncompliance", "data_type": "boolean", "required": True}],
            authority=SECURITY_AUTHORITY,
            priority=20,
        ),
    ]


def build_package(version_number, effective_from, contractor_threshold_days, is_active):
    return {
        "version_number": version_number,
        "effective_from": effective_from,
        "approved_by": "policy-governance-board",
        "is_active": is_active,
        "rules": build_rules(contractor_threshold_days),
    }


out_dir = Path(__file__).resolve().parent / "samples" / "policies"
out_dir.mkdir(parents=True, exist_ok=True)

(out_dir / "hardware-policy-v3.2-import.json").write_text(
    json.dumps(build_package(1, "2026-04-01", 20, False), indent=2), encoding="utf-8"
)
(out_dir / "hardware-policy-v3.3-import.json").write_text(
    json.dumps(build_package(2, "2026-10-01", 10, True), indent=2), encoding="utf-8"
)
print("wrote", out_dir / "hardware-policy-v3.2-import.json")
print("wrote", out_dir / "hardware-policy-v3.3-import.json")

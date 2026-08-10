"""Cross-domain source fixtures for the context-preserving ingestion pipeline.

These exist to make one architectural claim testable: **the ingestion core is
domain neutral.** The same assembler, the same relationship discovery and the
same reconciliation must handle an IT hardware catalogue, a labour-law article, a
procurement approval ladder, a compliance control and an operating procedure —
with no branch anywhere in shared code that knows which is which.

Each fixture is deliberately built around the *structures* that break naive
pipelines rather than around subject matter:

* ``it_hardware`` — a table whose rows are meaningless without their headers,
  plus a general condition and a precedence rule in a later subsection.
* ``labor_law`` — a numbered article, a definition its exclusion depends on, a
  statutory exclusion, and an explicit cross-reference to another article.
* ``finance_procurement`` — overlapping approval bands, an explicit currency, and
  an aggregate cap that spans the bands.
* ``compliance`` — a prohibition, an exception to it, an evidence requirement and
  a retention deadline under a named authority.
* ``ordered_procedure`` — numbered steps with an approval, a timeout, an
  escalation and a compensating action.

The **HR** fixtures at the end are regression data, not design input: they
reproduce the three concrete failures observed in the Workplace hardware
document. They are asserted against by name in
``tests/unit/test_hr_ingestion_regression.py``, and nothing in ``src/`` may
branch on them.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from policy_platform.contracts.policy_context import SourceElement


@dataclass
class DomainFixture:
    """One synthetic source document, already in canonical element form."""

    name: str
    elements: list[SourceElement] = field(default_factory=list)

    @property
    def by_id(self) -> dict[str, SourceElement]:
        return {element.element_id: element for element in self.elements}

    def element(self, element_id: str) -> SourceElement:
        return self.by_id[element_id]


class _Builder:
    """Terse construction of ordered elements with correct section paths."""

    def __init__(self) -> None:
        self._elements: list[SourceElement] = []
        self._path: list[str] = []
        self._table_rows: dict[str, int] = {}

    def heading(self, element_id: str, text: str) -> "_Builder":
        from policy_platform.infrastructure import source_structure

        self._path = source_structure.push_heading(self._path, text)
        return self._add(element_id, "heading", text)

    def para(self, element_id: str, text: str) -> "_Builder":
        return self._add(element_id, "paragraph", text)

    def item(self, element_id: str, text: str) -> "_Builder":
        return self._add(element_id, "list_item", text)

    def row(
        self, element_id: str, table_id: str, headers: list[str], cells: list[str]
    ) -> "_Builder":
        index = self._table_rows.get(table_id, 0)
        self._table_rows[table_id] = index + 1
        return self._add(
            element_id,
            "table_row",
            " | ".join(cells),
            table_id=table_id,
            table_headers=headers,
            table_row_index=index,
            table_cells=cells,
        )

    def _add(self, element_id: str, element_type: str, text: str, **kwargs) -> "_Builder":
        from policy_platform.infrastructure import source_structure

        self._elements.append(
            SourceElement(
                element_id=element_id,
                element_ref=element_id,
                element_type=element_type,
                order=len(self._elements),
                text=text,
                section=self._path[-1] if self._path else None,
                section_path=list(self._path),
                page=1,
                references=source_structure.detect_references(text),
                **kwargs,
            )
        )
        return self

    def build(self, name: str) -> DomainFixture:
        return DomainFixture(name=name, elements=self._elements)


# ---------------------------------------------------------------------------
# IT / hardware: table headers plus replacement and warranty precedence
# ---------------------------------------------------------------------------

_IT_HEADERS = ["Role profile", "Standard device", "Approval", "Cost ceiling"]


def it_hardware_fixture() -> DomainFixture:
    return (
        _Builder()
        .heading("IT-H1", "2. Device entitlement")
        .para(
            "IT-P1",
            "Each employee is entitled to one primary device selected from the approved "
            "catalogue according to the role profile table below.",
        )
        .row("IT-R1", "t-devices", _IT_HEADERS, ["General office", "Standard laptop, 14-inch", "On request, manager approval", "USD 1,150"])
        .row("IT-R2", "t-devices", _IT_HEADERS, ["Field engineer", "Ruggedised laptop", "Manager and IT approval", "USD 2,400"])
        .row("IT-R3", "t-devices", _IT_HEADERS, ["Design and media", "Mobile workstation", "Manager and department head approval", "USD 3,200"])
        .heading("IT-H2", "4. Replacement")
        .para(
            "IT-P2",
            "A device may be replaced when it can no longer support the work assigned to the "
            "holder, and not merely because a newer model is preferred.",
        )
        .heading("IT-H3", "4.1 Faulty equipment")
        .para(
            "IT-P3",
            "Faulty equipment must first be diagnosed by IT support before any replacement is "
            "arranged.",
        )
        .para(
            "IT-P4",
            "Where the device remains under manufacturer warranty, the warranty repair route "
            "takes precedence over replacement.",
        )
        .para(
            "IT-P5",
            "A device that has required repair on three or more separate occasions in twelve "
            "months may be replaced without further diagnosis.",
        )
        .build("it_hardware")
    )


# ---------------------------------------------------------------------------
# Labour law: article, definition dependency, exclusion, cross-reference
# ---------------------------------------------------------------------------


def labor_law_fixture() -> DomainFixture:
    return (
        _Builder()
        .heading("LL-H1", "Article 2. Definitions")
        .para(
            "LL-P1",
            "\"Continuous service\" means service with the same employer that has not been "
            "interrupted by a period exceeding thirty consecutive days.",
        )
        .para(
            "LL-P2",
            "\"Seasonal worker\" means a worker engaged for a defined seasonal period declared "
            "by the competent authority.",
        )
        .heading("LL-H2", "Article 74. Annual leave")
        .para(
            "LL-P3",
            "A worker who has completed one year of continuous service is entitled to paid "
            "annual leave of not less than twenty-one days.",
        )
        .para(
            "LL-P4",
            "The entitlement in this Article does not apply to a seasonal worker, whose leave "
            "is governed by Article 91.",
        )
        .heading("LL-H3", "Article 91. Seasonal engagement")
        .para(
            "LL-P5",
            "A seasonal worker accrues leave in proportion to the days actually worked during "
            "the declared season.",
        )
        .build("labor_law")
    )


# ---------------------------------------------------------------------------
# Finance / procurement: overlapping bands, currency, aggregate cap
# ---------------------------------------------------------------------------

_FIN_HEADERS = ["Band", "Amount (USD)", "Approver", "Secondary approver"]


def finance_procurement_fixture() -> DomainFixture:
    return (
        _Builder()
        .heading("FIN-H1", "3. Purchase approval")
        .para(
            "FIN-P1",
            "Every purchase commitment must be approved before the order is placed, at the "
            "level shown in the approval ladder below.",
        )
        .row("FIN-R1", "t-bands", _FIN_HEADERS, ["Band A", "Up to 5,000", "Line manager", "Not required"])
        .row("FIN-R2", "t-bands", _FIN_HEADERS, ["Band B", "5,000 to 50,000", "Department head", "Finance business partner"])
        .row("FIN-R3", "t-bands", _FIN_HEADERS, ["Band C", "Above 50,000", "Finance director", "Chief financial officer"])
        .para(
            "FIN-P2",
            "Amounts are stated in United States dollars; a commitment in another currency is "
            "converted at the rate published on the commitment date.",
        )
        .heading("FIN-H2", "3.1 Aggregate limit")
        .para(
            "FIN-P3",
            "Commitments to a single supplier may not exceed 250,000 in aggregate in any "
            "financial year, irrespective of the band of each individual commitment.",
        )
        .para(
            "FIN-P4",
            "The approver of a commitment may not be the person who raised the requisition.",
        )
        .build("finance_procurement")
    )


# ---------------------------------------------------------------------------
# Compliance: prohibition, exception, evidence requirement, retention, authority
# ---------------------------------------------------------------------------


def compliance_fixture() -> DomainFixture:
    return (
        _Builder()
        .heading("CMP-H1", "5. Restricted data handling")
        .para(
            "CMP-P1",
            "Restricted data must not be transferred to a system outside the approved "
            "processing environment.",
        )
        .para(
            "CMP-P2",
            "By exception, a transfer may proceed where the data protection officer has "
            "granted written authorisation for a named recipient and a stated purpose.",
        )
        .para(
            "CMP-P3",
            "Each authorised transfer must be evidenced by a signed authorisation record "
            "identifying the recipient, the purpose and the data categories.",
        )
        .heading("CMP-H2", "5.1 Retention")
        .para(
            "CMP-P4",
            "Authorisation records must be retained for seven years from the date of transfer.",
        )
        .para(
            "CMP-P5",
            "Where this section conflicts with a binding regulatory instruction, the "
            "regulatory instruction prevails and section 5 is applied to the extent it is "
            "not inconsistent.",
        )
        .build("compliance")
    )


# ---------------------------------------------------------------------------
# Ordered procedure: steps, approval, timeout, escalation, compensation
# ---------------------------------------------------------------------------


def ordered_procedure_fixture() -> DomainFixture:
    return (
        _Builder()
        .heading("PRC-H1", "7. Access request procedure")
        .para(
            "PRC-P1",
            "The following steps are performed in order; a later step may not begin until the "
            "preceding step has completed.",
        )
        .item("PRC-S1", "1. The requester submits the access request naming the system and the business need.")
        .item("PRC-S2", "2. The line manager approves or declines the request.")
        .item("PRC-S3", "3. Where the line manager has not responded within two working days, the request is escalated to the department head.")
        .item("PRC-S4", "4. The system owner provisions the access and records the provisioning reference.")
        .heading("PRC-H2", "7.1 Reversal")
        .para(
            "PRC-P2",
            "Where access is provisioned in error, the system owner revokes it and records a "
            "reversal reference against the original provisioning reference.",
        )
        .build("ordered_procedure")
    )


# ---------------------------------------------------------------------------
# HR regression data (test data only — never a shared-code branch)
# ---------------------------------------------------------------------------

_HR_HEADERS = ["Role profile", "Standard device", "Approval", "Cost ceiling"]


def hr_workplace_fixture() -> DomainFixture:
    """The three observed Workplace-hardware failures, as source.

    1. **Table 2.1 header + row** — the row was formulated without column
       meanings because Stage 1 discarded table headings and Stage 2 received
       only passage text.
    2. **Contractor ten-working-day threshold** — the threshold was in the first
       sentence and the consequence in the second; the canonical rule kept only
       the second, leaving "shorter" with no operator.
    3. **General replacement plus diagnostics/warranty across the former batch
       boundary** — the general replacement clause was the last element of batch
       2 and faulty equipment began batch 3, with no overlap.
    """

    return (
        _Builder()
        .heading("HR-H1", "2. Entitlement")
        .para(
            "HR-P1",
            "Each employee is entitled to one primary device from the approved catalogue, "
            "selected according to the role profile in Table 2.1.",
        )
        .row("HR-R1", "t2-1", _HR_HEADERS, ["General office", "Standard laptop, 14-inch", "On request, manager approval", "USD 1,150"])
        .row("HR-R2", "t2-1", _HR_HEADERS, ["Field engineer", "Ruggedised laptop", "Manager and IT approval", "USD 2,400"])
        .heading("HR-H2", "3. Contractors")
        .para(
            "HR-P2",
            "A contractor engaged for longer than ten working days is allocated equipment "
            "under this policy. Shorter periods are served from the loan equipment pool and "
            "do not create a permanent allocation.",
        )
        .heading("HR-H3", "4. Replacement")
        .para(
            "HR-P3",
            "A device may be replaced when it can no longer support the work assigned to the "
            "holder, and not merely because a newer model is preferred.",
        )
        .heading("HR-H4", "4.1 Faulty equipment")
        .para(
            "HR-P4",
            "Faulty equipment must first be diagnosed by IT support before a replacement is "
            "arranged.",
        )
        .para(
            "HR-P5",
            "Where the device remains under manufacturer warranty, the warranty repair route "
            "takes precedence over replacement.",
        )
        .build("hr_workplace")
    )


#: Every non-HR fixture, for the tests that assert the pipeline behaves
#: identically across domains.
CROSS_DOMAIN_FIXTURES = (
    it_hardware_fixture,
    labor_law_fixture,
    finance_procurement_fixture,
    compliance_fixture,
    ordered_procedure_fixture,
)

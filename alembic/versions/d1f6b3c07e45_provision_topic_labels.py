"""A generated subject name for a policy, stored where it cannot be mistaken for the source.

A policy card is titled by the heading the document wrote over it. That is the
right title and it stays the title. But a queue is not read in document order,
and a heading written for somebody reading in order routinely names nothing on
its own — it numbers a section, or repeats the words above it, or is a clause of
the sentence beneath. A reviewer scanning the queue then cannot tell what a card
is about without opening it.

This adds a second, generated string beside the heading: a few words naming the
subject the passage is about.

Why a table and not a column
----------------------------

`document_provisions` holds the document's own headings and nothing else, and
`test_a_provision_composes_no_text.py` forbids a prose column on it by name. A
`topic_label` column there would put a string this system composed inside the
row a reader trusts to be a copy of the source. Kept in its own table, the label
is distinguishable from the document's words by where it is stored — which no
later reader can misread and no later query can accidentally join away.

Provenance is the second reason. A generated string with no record of the model,
the instruction and the words it was generated from is a claim with no history.
Four columns describing a fifth do not belong on a table whose whole contract is
that it copies.

Exactly one outcome per row
---------------------------

`label_text` and `unavailable_code` are exclusive, enforced by a check
constraint. That is what keeps three states apart: no row means nobody has
asked, a label means this is it, and a code means it was asked for and nothing
usable came back. Without the constraint the third state could silently become
a row holding neither, and the interface would show a blank where a document's
heading should be.

Nothing is backfilled
---------------------

A label is produced by a model call. There is no SQL that can write one, and
writing a placeholder would be this system naming a document's subject out of
its own vocabulary. Existing provisions therefore have no row, which renders as
"no label has been generated" — a true statement, and the state the interface is
built to show.

Revision ID: d1f6b3c07e45
Revises: b8e1c5f70a92
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "d1f6b3c07e45"
down_revision = "b8e1c5f70a92"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "provision_topic_labels",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("provision_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("label_text", sa.Text(), nullable=True),
        sa.Column("unavailable_code", sa.String(length=50), nullable=True),
        sa.Column("model_deployment", sa.String(length=200), nullable=True),
        sa.Column("prompt_version", sa.String(length=50), nullable=False),
        sa.Column("source_digest", sa.String(length=64), nullable=False),
        sa.Column("source_rule_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        # CASCADE, unlike the SET NULL on `candidate_rules.provision_id`. A rule
        # survives losing its policy; a label about a provision that no longer
        # exists is about nothing, and keeping it would leave a generated string
        # in the database with no source to check it against.
        sa.ForeignKeyConstraint(
            ["provision_id"], ["document_provisions.id"], ondelete="CASCADE"
        ),
        # One current label per provision. A card shows one, and a second row
        # would make "which one" a question the reader has to answer.
        sa.UniqueConstraint("provision_id", name="uq_provision_topic_labels_provision"),
        sa.CheckConstraint(
            "(label_text IS NULL) <> (unavailable_code IS NULL)",
            name="ck_provision_topic_labels_one_outcome",
        ),
    )


def downgrade() -> None:
    op.drop_table("provision_topic_labels")

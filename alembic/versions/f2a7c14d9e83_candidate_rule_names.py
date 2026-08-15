"""A generated handle for what one rule is for, stored outside the rule's record.

A policy card lists the rules drawn from one passage. Sibling rules come from
the same few sentences, so several of them open with the same words and differ
only deep in the clause; the identifier beside each is a hash. A reviewer
scanning the card cannot tell them apart without reading all of them in full,
every time the card is drawn.

This adds a short generated line per rule saying what that rule is *for* — a
handle for finding and distinguishing, never a substitute for reading the rule.

Why a table and not a field on the rule
---------------------------------------

`candidate_rules.payload_json` is a record of what a document states. It is
exported, it is published, and a reviewer opens it to check the extraction
against the source. A generated handle is this system's commentary on that
record. Inside the payload it would leave in every export and every published
version, and a reader downstream would find words in a policy record that no
document stated and no extraction produced.

Stored here, keyed by the rule it describes, it is reachable only by asking for
it by name. Nothing in the read path of a rule can pick one up by accident,
which is a stronger guarantee than a convention that nobody adds it to the
payload.

Exactly one outcome per row
---------------------------

`name_text` and `unavailable_code` are exclusive, enforced by a check
constraint, for the reason `provision_topic_labels` gives: it keeps three states
apart. No row means nobody has asked; a name means this is it; a code means it
was asked for and nothing usable came back. The third has to be storable or
every run would ask again about the same rules and pay again for the same
answer.

Nothing is backfilled
---------------------

A name is produced by a model call. There is no SQL that can write one, and a
placeholder would be this system inventing a handle out of its own vocabulary.
Existing rules therefore have no row, and a rule with no row renders exactly as
it did before this migration.

Revision ID: f2a7c14d9e83
Revises: c4b1e83f0a57
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "f2a7c14d9e83"
down_revision = "c4b1e83f0a57"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "candidate_rule_names",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("candidate_rule_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name_text", sa.Text(), nullable=True),
        sa.Column("unavailable_code", sa.String(length=50), nullable=True),
        sa.Column("model_deployment", sa.String(length=200), nullable=True),
        sa.Column("prompt_version", sa.String(length=50), nullable=False),
        sa.Column("source_digest", sa.String(length=64), nullable=False),
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
        # CASCADE. A handle for a rule that no longer exists is a handle for
        # nothing, and keeping it would leave a generated string in the database
        # with no record to check it against.
        sa.ForeignKeyConstraint(
            ["candidate_rule_id"], ["candidate_rules.id"], ondelete="CASCADE"
        ),
        # One current name per rule: the card shows one.
        sa.UniqueConstraint("candidate_rule_id", name="uq_candidate_rule_names_rule"),
        sa.CheckConstraint(
            "(name_text IS NULL) <> (unavailable_code IS NULL)",
            name="ck_candidate_rule_names_one_outcome",
        ),
    )


def downgrade() -> None:
    op.drop_table("candidate_rule_names")

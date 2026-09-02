"""Application settings loaded from environment (.env) — Section 5/Section 23.

Single source of truth for configuration; no component should read
`os.environ` directly outside this module.
"""
from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    environment: str = "development"
    log_level: str = "INFO"

    postgres_host: str = "localhost"
    postgres_port: int = 5433
    postgres_db: str = "policy_platform"
    postgres_user: str = "policy_admin"
    postgres_password: str = "policy_admin_pw"

    database_url: str
    alembic_database_url: str

    api_host: str = "0.0.0.0"
    api_port: int = 8000
    dev_auth_enabled: bool = True
    #: When True, the RBAC layer enforces capability-band checks on every
    #: request.  Defaults to False so the existing test suite — which calls
    #: endpoints with no credentials — continues to pass unmodified.
    rbac_enabled: bool = False

    # ── identity ────────────────────────────────────────────────────
    #: Entra (or any OIDC issuer) settings. All three are needed before a
    #: bearer token can be validated; with any of them unset the token path
    #: is simply not offered, rather than half-checked. A partially verified
    #: token is worse than an unverified one, because it looks verified.
    entra_issuer: str | None = None
    entra_audience: str | None = None
    entra_jwks_url: str | None = None

    #: Whether `X-MS-CLIENT-PRINCIPAL` may be believed.
    #:
    #: Off by default, and the default is the security decision. The
    #: platform injects that header after authenticating someone, but in
    #: this deployment the browser reaches nginx, which proxies to the API
    #: and forwards headers it was not told to drop — so a caller who sets
    #: the header themselves has it delivered alongside the genuine one.
    #: The API being internal-only does not help: the web container is
    #: inside the perimeter and forwards whatever it is handed.
    #:
    #: Turn this on only where the edge provably strips inbound copies.
    #: `apps/web/nginx.conf.template` now clears them, which is what makes
    #: enabling it defensible there; a different ingress is a different
    #: question and has to be answered before this is set.
    trust_platform_auth_header: bool = False

    # ── subscription key (one fixed key for a system caller) ────────
    #: A single pre-shared key that authenticates a non-interactive caller —
    #: an agent, a workflow, a scheduled job — in the header
    #: `X-Policy-Subscription-Key`.
    #:
    #: Unset (the default) the mechanism does not exist: the header is not
    #: read, and no request can be authenticated by it. That is the same
    #: posture as `entra_issuer` and `local_accounts_enabled` — a credential
    #: path that has not been configured is not offered rather than offered
    #: weakly.
    #:
    #: It is deliberately *one* key, not a keyring. This increment gives an
    #: operator a way to let one system call the audited decision API without
    #: standing up an issuer; it does not give them per-caller attribution,
    #: because every request presenting this key resolves to the same identity
    #: below. Rotation is: change the value, restart the API. There is no
    #: overlap window and no revocation list, and inventing either without a
    #: store to hold them would be a claim rather than a feature.
    policy_subscription_key: str | None = None
    #: The identity a subscription-key caller is recorded as. It appears in
    #: every audited receipt that key produces, so it should name the system,
    #: not a person.
    policy_subscription_key_identity: str = "external-api-client"
    #: The role that identity holds. Defaults to the lowest privilege on
    #: purpose: a key is a bearer credential with no expiry, and the blast
    #: radius of one that leaks should be a read, not a publication. Validated
    #: against the role vocabulary at use; an unknown value is refused rather
    #: than silently treated as an unrecognised — and therefore unsatisfiable —
    #: role. Written as a literal rather than imported from `api.roles` because
    #: infrastructure must not import the API layer.
    policy_subscription_key_role: str = "viewer"

    # ── local accounts (development sign-in) ────────────────────────
    #: When True, the API reads a plaintext accounts file and issues JWTs
    #: signed with a locally held RSA key. The tokens are validated by the
    #: same path as Entra tokens — no bypass — so what is tested locally is
    #: what will run in production.
    local_accounts_enabled: bool = False
    local_accounts_file: str = ".local-accounts.txt"
    local_token_ttl_minutes: int = 480
    local_signing_key_file: str = ".local-signing-key.pem"
    local_token_issuer: str = "policyverbatim-local"
    local_token_audience: str = "policyverbatim-api"

    web_dev_server_port: int = 5173
    vite_api_base_url: str = "http://localhost:8000"
    #: Comma-separated browser origins allowed to call the API. Empty means
    #: "derive them", which is the developer-friendly default.
    #:
    #: Previously the allowlist was a hardcoded port range inside the app
    #: factory, so running the UI on any other port meant editing application
    #: code — and the resulting failure is a silent CORS block in the browser
    #: rather than a server-side error anyone would see in a log.
    cors_allowed_origins: str = ""
    #: Ports probed when `cors_allowed_origins` is empty. Vite increments its
    #: port when the preferred one is taken, so a single port is not enough to
    #: make `npm run dev` reliably work out of the box.
    cors_dev_port_range: str = "5173-5180"

    # Azure OpenAI (chat/extraction/rewrite/quality + embeddings). All
    # optional so the app still boots with AI features disabled if unset.
    #
    # TWO REASONING DEPLOYMENTS, ASSIGNED PER STAGE BY COMPLEXITY.
    #
    # Both roles below are now `gpt-5.6-*` reasoning deployments and both run at
    # `medium` reasoning effort. Neither is a "fast" or "cheap" tier: the split
    # is which model suits the work, measured rather than assumed.
    #
    #   `azure_openai_deployment` — the primary. `gpt-5.6-terra`. Everything on
    #   the decision and decision-light routes, which external callers consume:
    #   the intent classifier, the language boundary, the adjudication gathers,
    #   interactive chat, summaries, rewrite and quality. Measured over one
    #   interleaved 20x2 matrix it reached the same verdicts as `gpt-5.6-sol`
    #   while spending ~45% fewer reasoning tokens and holding a tighter tail.
    #
    #   `azure_openai_secondary_deployment` — `gpt-5.6-sol`. Used only on the
    #   policy-loading path, where extraction mixes the two: the passage stage
    #   copies rather than restructures and runs on the primary, while policy
    #   formulation is the most complex judgement in the pipeline and runs here.
    #
    # WHY THE DECISION ROUTE IS SINGLE-MODEL. The classifier and the language
    # boundary were briefly moved to the secondary deployment, which classified
    # more consistently in a small offline comparison. On the live route that
    # was not viable: in one 20x2 matrix the classifier stage reached 261,761 ms
    # on a call that spent 125 reasoning tokens. Work that cheap cannot take
    # four minutes of compute, so the cost is service-side — the deployment
    # throttling and this client's back-off retrying it — and it produced a
    # 306 s request against a documented 120 s client timeout. A slow stage on
    # the policy-loading path costs an ingestion job; the same stage on the
    # decision route costs a caller their request.
    #
    # WHY THERE IS NO LONGER A `temperature=0` DEPLOYMENT.
    #
    # This previously read: the fast deployment exists because it accepts
    # `temperature=0`, "the determinism control those two stages depend on".
    # That rationale did not survive being measured. Asked the same question
    # three times at `temperature=0`, `gpt-5.4-mini` classified
    # `hw-contractor-15-days` as informational, informational, then decision —
    # so the stability the parameter was there to buy was not being delivered.
    # On the same scenario both reasoning deployments answered `decision` every
    # time, which is also the classification that scenario needs.
    #
    # `seed` is accepted by every deployment here and was separately measured to
    # change nothing (see `AzureOpenAIClient.chat`), and this resource returns a
    # null `system_fingerprint`. So no sampling control on offer delivers
    # run-to-run determinism, and the product does not claim one.
    #
    # Named deployments per model were declared here once and never read by
    # anything, so an operator setting them saw no effect. Routing is the two
    # roles below and nothing else.
    azure_openai_endpoint: str | None = None
    azure_openai_api_key: str | None = None
    azure_openai_api_version: str = "2024-12-01-preview"
    azure_openai_deployment: str | None = None
    azure_openai_secondary_deployment: str | None = None
    azure_openai_embedding_deployment: str | None = None
    azure_openai_embedding_model: str | None = None
    azure_openai_embedding_dimensions: int = 3072

    # Azure AI Search (clause-level RAG grounding for chat/extraction/quality).
    azure_search_endpoint: str | None = None
    azure_search_api_key: str | None = None
    azure_search_api_version: str = "2025-09-01"
    azure_search_authoring_index: str = "policy-authoring"
    azure_search_evidence_index: str = "policy-evidence"

    # Which parser turns an uploaded file into a canonical document at upload
    # time. This is a DIFFERENT concern from `docling_graph_enabled` below,
    # which selects a model-driven dense-extraction backend; the two must not
    # be conflated or share a flag. This one chooses a deterministic converter.
    #
    #   "legacy"  — `ingestion.document_ingestion.ingest_document`. Emits one
    #               element per table *row*, pipe-joining the cells, so a cell's
    #               column header is lost before any downstream stage sees it.
    #   "docling" — `docling.converter.convert_document`. Emits one element per
    #               table *cell* carrying row/column index and header identity,
    #               which is what `structural_graph` needs to build `header_for`
    #               / `table_cell_of` / `merged_with` edges and what
    #               `reading_plan._add_table_context` needs to tell the model
    #               which column a bare value sits under.
    #
    # Defaults to "legacy" — the behaviour in production today. The conformance
    # map (docs/specs/docling-integration-conformance-map.md) calls for Docling
    # to become primary, but that flip is a deliberate, evidence-backed decision
    # and not something this setting's default should make on anyone's behalf.
    #
    # Typed as a Literal so an unrecognised value fails loudly at startup.
    # Coercing an unknown value to "legacy" would silently downgrade a
    # structured parse to a flattened one, which is precisely the class of
    # defect this setting exists to fix.
    document_converter: Literal["legacy", "docling"] = "legacy"

    # Docling Graph dense extraction. Off by default: the dependency is an
    # optional extra (`pip install -e .[graph]`), and importing it in a runtime
    # that lacks it must fail as "disabled", not as a crash.
    docling_graph_enabled: bool = False
    #: LiteLLM model identifier. Left empty by default so it is *derived* from
    #: `azure_openai_deployment` rather than hardcoded: a literal default would
    #: keep pointing at one deployment after the platform's own was changed,
    #: which is exactly the silent drift the shared-configuration rule exists to
    #: prevent. Set it explicitly only to route extraction at a different model
    #: on purpose.
    docling_graph_model: str = ""

    @property
    def ai_enabled(self) -> bool:
        """True only when both Azure OpenAI chat and embeddings are configured."""

        return bool(
            self.azure_openai_endpoint
            and self.azure_openai_api_key
            and self.azure_openai_deployment
            and self.azure_openai_embedding_deployment
        )

    @property
    def allowed_cors_origins(self) -> list[str]:
        """Browser origins permitted to call the API.

        An explicit `CORS_ALLOWED_ORIGINS` wins outright: an operator who names
        origins means those and no others, and quietly unioning them with a
        development range would widen production beyond what was asked for.

        With nothing set, the configured UI port and the Vite fallback range are
        allowed on both `localhost` and `127.0.0.1`. Both hostnames are needed
        because they are different origins to a browser, and which one a
        developer types is not predictable.
        """

        explicit = [origin.strip() for origin in self.cors_allowed_origins.split(",")]
        explicit = [origin for origin in explicit if origin]
        if explicit:
            return explicit

        ports = {self.web_dev_server_port, *self._dev_port_range()}
        return [f"http://localhost:{port}" for port in sorted(ports)] + [
            f"http://127.0.0.1:{port}" for port in sorted(ports)
        ]

    def _dev_port_range(self) -> range:
        """Parse `cors_dev_port_range`, falling back rather than failing to boot.

        A malformed range is a configuration typo. Refusing to start over it
        would turn a cosmetic mistake into an outage, so the documented default
        is used instead.
        """

        try:
            low, _, high = self.cors_dev_port_range.partition("-")
            return range(int(low), int(high) + 1)
        except (TypeError, ValueError):
            return range(5173, 5181)

    @property
    def search_enabled(self) -> bool:
        return bool(self.azure_search_endpoint and self.azure_search_api_key)

    @property
    def graph_extraction_model(self) -> str:
        """LiteLLM identifier for dense extraction.

        Derived from the platform's own chat deployment unless overridden, so
        changing the deployment moves extraction with it. Two independently
        configured models drift, and the resulting failure is a run extracted by
        a different model than the one that was validated.
        """

        if self.docling_graph_model:
            return self.docling_graph_model
        return f"azure/{self.azure_openai_deployment}" if self.azure_openai_deployment else ""

    @property
    def graph_extraction_enabled(self) -> bool:
        """True when dense extraction can actually run.

        Deliberately requires a chat endpoint, key and deployment but *not* an
        embedding deployment: dense extraction never embeds anything, and
        gating it on `ai_enabled` would make it unavailable in an environment
        that is perfectly capable of running it.
        """

        return bool(
            self.docling_graph_enabled
            and self.azure_openai_endpoint
            and self.azure_openai_api_key
            and self.azure_openai_deployment
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()

# Security roadmap

**Status: pending.** The current Local deployment is for a trusted environment.

## Current gaps

- The header actor/persona is workflow attribution, not authentication.
- The API does not validate user tokens.
- Manager checks trust a client-supplied role.
- Azure OpenAI and Azure AI Search use API keys.
- PostgreSQL uses password authentication.
- The Azure Files mount uses a storage account key.

## Required work

### Authentication and authorization

- Register separate Entra applications for the SPA and API.
- Validate access tokens in FastAPI.
- Store application/project membership and roles in PostgreSQL.
- Guard each endpoint with an explicit permission.
- Derive audit attribution from the validated principal.
- Remove actor and role fields as authorization inputs.

### Managed identity

- Use managed identity for Azure OpenAI and Azure AI Search.
- Use Entra authentication for PostgreSQL where supported.
- Retain ACR and Key Vault managed identities.
- Introduce a document-storage abstraction before replacing the key-based Azure
  Files mount.

### Platform hardening

- Add security headers and document-content controls.
- Add retry/backoff for transient Azure failures.
- Add code-level tracing and alerts.
- Validate private DNS, endpoints, backup, restore, and rollback in Azure.

## Completion criteria

- No client-controlled value can grant authorization.
- Every mutation has a server-side permission.
- Audit identity comes from a verified principal.
- Managed identity replaces supported long-lived keys.
- Live Azure smoke, negative, recovery, and rollback tests pass.

References:

- [Microsoft identity platform](https://learn.microsoft.com/entra/identity-platform/)
- [Keyless Azure AI connections](https://learn.microsoft.com/azure/developer/ai/keyless-connections)
- [Azure AI Search RBAC](https://learn.microsoft.com/azure/search/search-security-rbac)

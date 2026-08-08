import type { PolicyScope } from "./api";

export const EMPTY_SCOPE: PolicyScope = { jurisdictions: [], organizational_units: [], personas: [], processes: [] };

/** Always returns a fully-populated PolicyScope, defaulting any missing
 * dimension to an empty (= unrestricted) array. Mirrors the backend's
 * `_safe_scope()` fail-open convention (see ai_extraction.py / ADR-0008):
 * an absent or malformed dimension always means "applies to everyone/
 * everywhere", never a guessed restriction. */
export function normalizeScope(scope: Partial<PolicyScope> | null | undefined): PolicyScope {
  return {
    jurisdictions: scope?.jurisdictions ?? [],
    organizational_units: scope?.organizational_units ?? [],
    personas: scope?.personas ?? [],
    processes: scope?.processes ?? [],
  };
}

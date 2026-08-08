/**
 * Small in-memory cache resolving a document version's clauses (fetched once
 * via GET /api/documents/{document_version_id}/clauses) so every RuleCard on a
 * page — potentially dozens, mostly sharing the same source document — can
 * resolve `evidence[].clause_id` back to real verbatim source text without a
 * network round trip per rule.
 */
import { api, type Clause } from "./api";

const cache = new Map<string, Promise<Clause[]>>();

export function getClausesForDocumentVersion(documentVersionId: string): Promise<Clause[]> {
  let entry = cache.get(documentVersionId);
  if (!entry) {
    entry = api.getDocumentClauses(documentVersionId).catch((err) => {
      cache.delete(documentVersionId); // don't poison the cache with a transient failure
      throw err;
    });
    cache.set(documentVersionId, entry);
  }
  return entry;
}

/** Resolve every clause referenced by `documentVersionIds`, returning a lookup by clause id. */
export async function resolveClausesById(documentVersionIds: string[]): Promise<Map<string, Clause>> {
  const unique = [...new Set(documentVersionIds)];
  const lists = await Promise.all(
    unique.map((id) => getClausesForDocumentVersion(id).catch(() => [] as Clause[]))
  );
  const byId = new Map<string, Clause>();
  for (const list of lists) {
    for (const clause of list) byId.set(clause.id, clause);
  }
  return byId;
}

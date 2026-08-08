/**
 * Small in-memory cache resolving a document *version* id back to its parent
 * document's title and a human version label (e.g. "v3") — so a RuleCard's
 * evidence citation can show "Expense Policy Handbook · v3" instead of a
 * bare UUID, without every card issuing its own document-list request.
 * Mirrors clauseCache.ts's caching approach, one level up (documents, not
 * clause text).
 */
import { api, type SourceDocument } from "./api";

export interface DocumentMeta {
  documentTitle: string;
  versionLabel: string;
}

let allDocumentsPromise: Promise<SourceDocument[]> | null = null;

function loadAllDocuments(): Promise<SourceDocument[]> {
  if (!allDocumentsPromise) {
    allDocumentsPromise = api.listDocuments().catch((err) => {
      allDocumentsPromise = null; // don't poison the cache with a transient failure
      throw err;
    });
  }
  return allDocumentsPromise;
}

/** Resolve every document version referenced by `documentVersionIds`, returning a lookup by version id. */
export async function resolveDocumentMetaByVersionId(
  documentVersionIds: string[]
): Promise<Map<string, DocumentMeta>> {
  const byId = new Map<string, DocumentMeta>();
  if (documentVersionIds.length === 0) return byId;
  const docs = await loadAllDocuments().catch(() => [] as SourceDocument[]);
  for (const doc of docs) {
    for (const v of doc.versions) {
      byId.set(v.id, { documentTitle: doc.title, versionLabel: `v${v.version_number}` });
    }
  }
  return byId;
}

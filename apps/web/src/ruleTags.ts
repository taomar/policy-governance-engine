/**
 * Tags the extraction applies to a rule, mirrored from the server.
 *
 * Kept in one module so a tag string is written once on this side. The server
 * definition is `DOCUMENT_GUIDANCE_TAG` in
 * `infrastructure/formulation_mapping.py`; the two must agree, and a mismatch
 * silently hides the badge rather than failing, so the coupling is named here
 * rather than left as a literal at each use site.
 */

/**
 * The statement's subject is the document itself — what it is, who it is for,
 * or how to read it — rather than anyone it governs.
 *
 * Such a rule is kept for review and made non-enforcing, never dropped:
 * deciding that a sentence carries no policy is the reviewer's call.
 */
export const DOCUMENT_GUIDANCE_TAG = "document_guidance";

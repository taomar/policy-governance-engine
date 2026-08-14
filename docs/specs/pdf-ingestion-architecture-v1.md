# PDF INGESTION AND POLICY EXTRACTION ARCHITECTURE

- **Target implementation agent:** Claude Opus
- **Platform:** Azure AI Search + embeddings + Azure OpenAI
- **Primary requirement:** exhaustive, verbatim policy extraction

**IMPORTANT:**

This instruction governs HOW documents are parsed, chunked, indexed,
reconstructed and supplied to the policy-extraction LLM.

Policy extraction itself is performed by a separate strict-verbatim
policy-passage extraction prompt.


---

## STATUS — added 2026-08-14, not part of the original instruction

**This document predates the code. It is still normative and still cited, but
it is not a description of the system as built.** Part of it was never
implemented, and one part of it should stay that way. Read it together with
[`docs/failures/designed-pipeline-and-running-pipeline.md`](../failures/designed-pipeline-and-running-pipeline.md),
which records where the designed pipeline and the running one diverge.

Provenance: the file arrived in commit `7093f3b` and no line below this section
has been edited since. The code cites it as normative —
`infrastructure/ingestion/document_ingestion.py` line 3 names this file by
path, and `contracts/canonical_document.py` cites eleven of its sections. The
original wording is preserved deliberately: it is the record of what was asked
for, not a description to be kept current.

### The prompt this document refers to

The preamble above refers to "a separate strict-verbatim policy-passage
extraction prompt". It lives at
`src/policy_platform/infrastructure/prompts/passage_extractor_v1.md` and is
loaded from disk by `infrastructure/extraction/passage_extractor.py`, so a
revision to it is a visible file change rather than a diff buried in Python.
That is the only copy that runs.

A second copy sat in `docs/specs/verbatim-passage-extractor-v1.md` until
2026-08-14, when it was deleted. Its name said v1 and its version number agreed
with the running one, but it was **an old intermediate state of v1** — which is
worse than being out of date openly, because both signals said it was current.
It had missed both revisions the runtime asset received: commit `0069b40`,
which added the rule excluding a document's statements about its own
enactment, approval, effective date and supersession, and commit `5846393`,
which removed currency-specific wording. It stood 32 lines and 1,760 bytes
behind. A reader building from it would have produced a system that extracts
the document-control metadata the running system deliberately rejects.

The general form, which is why this is recorded here rather than in a note of
its own: **a prompt copied into documentation is a source artefact wearing the
wrong clothes, and it drifts faster than code because nothing imports it.** The
domain-neutrality guard scans `src/` and the prompt directory, not `docs/`, so
the stale copy kept wording the runtime prompt had already had removed and no
test could see it. Nothing that is never loaded can fail loudly.
`tests/unit/test_a_runtime_asset_has_one_home.py` now holds the rule that
closes the class: a file the code loads at runtime has exactly one copy, and it
lives where the code loads it from.

### Implemented

Sections 6–13, 19, 26, 28–30, 35, 38, 39, 43–44, and the boundary tests of
sections 47–53.

* The canonical model of section 7 is `contracts/canonical_document.py`. The
  two representations of section 6 are `CanonicalPage.raw_text` and
  `CanonicalElement`.
* Cross-page reconstruction (sections 8–10) is
  `infrastructure/ingestion/document_ingestion.py`, which records every join as
  a named transformation — `cross_page_join`, `line_break_hyphen_join`.
* The verbatim guarantee of section 26 is enforced by `verify_verbatim`
  (`infrastructure/extraction/passage_extractor.py` line 215). Section 51's own
  test case — `non-Saudi` offered against a source reading `non- Saudi` — is
  rejected, as that section requires.
* Section 3's requirement is met: extraction enumerates a document rather than
  retrieving the top *k*. See **Overtaken** below for the mechanism.

### Built, but not reached by the running pipeline

The context-window architecture of sections 22–24 and the coverage proof of
section 40 are both implemented — `contracts/reading_plan.py` — and neither
reaches the extraction model. Section 22 is therefore unmet in effect while its
implementation is complete and tested. The evidence is in the failures record
cited above and is not repeated here.

### Never built

* **Sections 4 and 32 — lists and tables spanning pages.** A table continuing
  across a page break is not reassembled into one logical table. The converter
  emits each page's grid separately, so a body row on a continuation page has
  no header row to resolve against.
* **Section 16 — overlap between extraction windows.** Windows are strictly
  disjoint (`infrastructure/extraction/ai_extraction.py` lines 120–134), so a
  condition ending one window and its consequence beginning the next are never
  presented together. Section 42's deduplication requirement is dormant only
  because of this, and becomes live the moment overlap exists.
* **Section 41 — retry.** A window whose processing fails is recorded as a skip
  and the run still reports `completed`
  (`infrastructure/extraction/ai_extraction.py` line 1061). There is no retry in
  the path.
* **Section 14 — configurable chunk size.** `_MAX_CHARS_PER_BATCH` is a module
  constant, not a setting.
* **Sections 31, 33, 34 — table cell position, list nesting, footnote anchors.**
  Present on the canonical contract, dropped at the persistence boundary, so
  they never reach extraction.

### Overtaken — designed, never built, and not to be built

**Sections 18–21, and the ordering fields of section 36.** These specify an
Azure AI Search retrieval layer: `chunk_order`, `previous_chunk_id`,
`next_chunk_id`, `parent_element_ids`, `first_page`, `last_page`, and
extraction driven by a filtered, ordered query over the index. None of those
fields is written (`infrastructure/search/indexing.py`), and
`infrastructure/search/search_client.py` line 3 records that the client never
creates or alters index schemas.

**Do not implement them.** Their purpose was section 3's requirement — visit
every region of a document rather than retrieve the most similar *k* — and that
requirement is already met by a better mechanism: clauses are enumerated from
PostgreSQL in `Clause.sequence` order
(`infrastructure/extraction/ai_extraction.py` line 563), a total order the
index would otherwise have had to reconstruct. **The requirement stands; this
way of meeting it has been overtaken.** Sections 3, 21 and 45 remain in force,
and are satisfied.

Of section 36, what is built: embeddings are generated, and `document_id` is
filterable. What is not: the ordering fields above.

### Stated limitation — INVARIANT 7

INVARIANT 7 requires every extraction to be validated against canonical source
text. `verify_verbatim` is called against the *rendered batch* that was sent to
the model (`infrastructure/extraction/passage_extractor.py` lines 389 and 410),
not against `CanonicalPage.raw_text`. That proves the model copied rather than
composed. It does not prove the stored clause matches the PDF, so a document
whose text was captured wrongly upstream can pass verbatim verification against
its own corrupted store.

This limit is known and deliberately still open. Closing it means first deciding
what verification means once canonical text has been legitimately transformed:
section 30 permits hyphen-joining, while section 51 requires a repaired hyphen
to *fail* an exact comparison — so a single exact match against raw page text
cannot serve both.

---

## 1. OBJECTIVE

Implement a document ingestion and retrieval architecture for policy documents
such as:

- HR policies
- finance policies
- legal policies
- regulations
- compliance manuals
- procurement policies
- security standards
- operating procedures
- contracts
- governance documents

The architecture MUST ensure that:

1. The entire document is processed.
2. Text is never lost because of PDF page boundaries.
3. Paragraphs that continue onto another PDF page remain logically connected.
4. Lists that continue onto another page remain logically connected.
5. Tables that continue onto another page remain logically connected.
6. Policy extraction receives sufficient neighboring context.
7. The exact original source wording remains recoverable.
8. Extracted policy passages can be validated against source text.
9. Every extracted passage has precise document/page provenance.
10. Embedding chunk boundaries MUST NOT become policy boundaries.


## 2. CRITICAL ARCHITECTURAL PRINCIPLE

A PDF PAGE IS A PHYSICAL LAYOUT UNIT.

IT IS NOT NECESSARILY A SEMANTIC UNIT.

Never assume:

    page boundary == paragraph boundary

Never assume:

    page boundary == policy boundary

Never assume:

    Azure AI Search chunk == policy boundary

Never assume:

    embedding chunk == sentence boundary

Never assume:

    search result == complete policy passage


A paragraph may begin on page 24 and finish on page 25.

A numbered list may begin on page 30 and continue on page 31.

A table may begin on page 45 and continue on page 46.

A policy condition may appear at the bottom of one page while its consequence
appears on the next page.

The implementation MUST preserve these relationships.


## 3. DO NOT USE VECTOR SEARCH FOR EXHAUSTIVE EXTRACTION

This is CRITICAL.

Azure AI Search vector/hybrid search is useful for:

- user queries
- policy lookup
- contradiction detection
- similarity detection
- policy comparison
- later RAG operations

It MUST NOT be used as the sole mechanism for deciding which chunks of a
document are processed during initial policy extraction.

DO NOT do:

    vector search:
        "find policies in this document"

    top_k = 20

    process only returned chunks

This can miss valid policies.

Policy extraction requires DOCUMENT COVERAGE, not semantic retrieval.


Instead:

    filter Azure AI Search by document_id

    retrieve ALL chunks belonging to the document

    sort by deterministic document order

    process every chunk/window

Conceptually:

    SELECT *
    FROM SearchIndex
    WHERE document_id = X
    ORDER BY logical_order ASC


Every source region must be visited.


## 4. RECOMMENDED INGESTION PIPELINE

Preferred logical pipeline:

PDF / DOCX / source file
        ↓
layout-aware extraction
        ↓
physical pages + structural elements
        ↓
header/footer filtering
        ↓
logical block reconstruction
        ↓
cross-page continuation reconstruction
        ↓
stable canonical source representation
        ↓
semantic chunk construction
        ↓
embeddings
        ↓
Azure AI Search
        ↓
document coverage reader
        ↓
context-window assembler
        ↓
strict verbatim policy extractor
        ↓
exact-source validation


Do NOT:

PDF
   ↓
split every page independently
   ↓
embed pages
   ↓
search top-k
   ↓
extract policies


That architecture is insufficient for exhaustive policy extraction.


## 5. PARSING TECHNOLOGY

Use layout-aware document parsing.

For a new Azure AI Search ingestion implementation, evaluate:

    Azure Content Understanding skill

because it supports layout-aware semantic units and can preserve structures
that span page boundaries.

If the existing implementation already uses:

    Azure Document Intelligence Layout /
    Azure AI Search Document Layout skill

it may remain in use, but perform explicit logical continuation handling.

Do NOT rely only on plain PDF text extraction when layout structure is
important.


The parser should preserve, where available:

- page number
- paragraph/block role
- heading level
- text spans
- offsets
- bounding regions
- list structure
- table structure
- table row/column relationships
- document ordering


## 6. TWO REPRESENTATIONS MUST BE STORED

Maintain TWO distinct representations.


A. RAW SOURCE REPRESENTATION

Purpose:

    auditability
    verbatim validation
    forensic comparison

Never intentionally rewrite this representation.

Store source-derived text and coordinates exactly as provided by the selected
document extraction layer.


B. LOGICAL DOCUMENT REPRESENTATION

Purpose:

    LLM context
    policy detection
    semantic chunking

This representation may reconnect physical page fragments that clearly belong
to one logical paragraph/list/table.

IMPORTANT:

Reconnection MUST NOT invent words.

It can only concatenate source fragments in their original order.


## 7. CANONICAL DOCUMENT MODEL

Create a deterministic intermediate representation before embedding.

Example:

{
  "document_id": "...",
  "document_version": "...",
  "elements": [
    {
      "element_id": "E000001",
      "element_type": "paragraph",
      "logical_order": 1,
      "text": "...",
      "source_fragments": [
        {
          "page": 1,
          "source_offset_start": 100,
          "source_offset_end": 255
        }
      ]
    }
  ]
}


Possible element_type values:

    heading
    paragraph
    list
    list_item
    table
    table_row
    caption
    footnote
    other


Do not use LLM-generated text in this structure.


## 8. CROSS-PAGE PARAGRAPH RECONSTRUCTION

This is one of the most important requirements.

Example:

PAGE 10 ends:

    If an employee is absent from work for more than


PAGE 11 starts:

    thirty consecutive days without approval, the employer may terminate
    the employment relationship.


Do NOT create:

Chunk A:
    If an employee is absent from work for more than

Chunk B:
    thirty consecutive days without approval...


Instead reconstruct the logical paragraph from the source fragments.

The reconstructed logical text should remain source-derived:

    If an employee is absent from work for more than
    thirty consecutive days without approval, the employer may terminate
    the employment relationship.


Store provenance:

source_fragments:
[
    { "page": 10, ... },
    { "page": 11, ... }
]


The policy extractor must be able to receive the complete logical passage.


## 9. HOW TO DETECT CROSS-PAGE CONTINUATION

Do NOT use one heuristic alone.

Use multiple structural signals.

Potential continuation signals include:

- previous page ends without terminal punctuation
- previous block has paragraph role
- next page begins with paragraph content rather than a heading
- same indentation/style/font role when available
- same list numbering hierarchy
- same section/article
- next page begins with lowercase continuation text
- grammar strongly indicates continuation
- parser reports both fragments as related structural content
- table continues with matching columns
- repeated table heading indicates continuation
- article/list numbering continues sequentially


Potential boundary signals include:

- new heading
- new article
- new section
- clearly completed sentence
- major style change
- new numbered provision
- explicit page-independent structural boundary


Do NOT allow an LLM to invent missing joining text.


## 10. NEVER INSERT WORDS WHILE STITCHING

Cross-page reconstruction means:

    concatenate existing source fragments

It does NOT mean:

    rewrite them into better English.


Forbidden:

Page 10:
    The employee must obtain

Page 11:
    approval prior to travel.


Generated reconstruction:

    The employee must obtain manager approval prior to travel.


The word "manager" was invented.

This is forbidden.


Valid reconstruction:

    The employee must obtain approval prior to travel.


Only characters from source fragments may participate.


## 11. PAGE HEADERS AND FOOTERS

Repeated headers and footers frequently occur inside extracted PDF text.

Examples:

    Ministry of ...
    Confidential
    Page 32 of 140
    Corporate HR Policy

These can interrupt a sentence that continues across pages.


Detect repeated page furniture using:

- repeated text at similar page positions
- page-number patterns
- recurring document title
- recurring confidentiality labels
- recurring organization names


Do not inject repeated headers or footers into logical policy paragraphs.

However:

DO NOT delete them from the RAW representation.

Mark them structurally as:

    element_type = page_header

or:

    element_type = page_footer

and exclude them from logical policy text.


## 12. PARAGRAPHS ARE THE PRIMARY CHUNKING UNIT

Do not begin chunking by arbitrary character count.

First identify semantic/layout units:

    headings
    paragraphs
    lists
    tables


Then assemble those units into embedding chunks.

Preferred hierarchy:

DOCUMENT
   ↓
SECTION
   ↓
PARAGRAPH / LIST / TABLE
   ↓
CHUNK


Never:

DOCUMENT
   ↓
every 2,000 characters regardless of structure


Microsoft's layout-aware Search tooling is specifically intended to produce
more semantically coherent chunks; use that structural information instead of
discarding it.


## 13. CHUNK BOUNDARY RULE

Embedding chunks MUST be created only AFTER logical blocks have been
reconstructed.

A chunk boundary should preferably occur:

1. between sections
2. between paragraphs
3. between complete list structures
4. between tables
5. between complete sentences

Avoid splitting:

- a sentence
- a policy condition from its consequence
- an exception from the rule it modifies
- an introductory list statement from its items
- a table header from its rows
- a paragraph because of a physical PDF page boundary


## 14. CHUNK SIZE

Do not hard-code a tiny chunk size.

Select a configurable target appropriate to the embedding model and retrieval
requirements.

Example configuration concept:

    target_chunk_tokens = 800
    max_chunk_tokens = 1200
    overlap_tokens = 150


These numbers are examples, not mandatory values.

The important requirement is:

    SEMANTIC BOUNDARY > TARGET SIZE


If a complete logical paragraph slightly exceeds the preferred target size,
prefer keeping the paragraph intact when model limits permit.


## 15. OVERSIZED PARAGRAPHS

If a single logical paragraph exceeds the maximum allowable chunk size:

First attempt to split at:

    sentence boundary

Do NOT split at an arbitrary character position.

Store:

    parent_element_id

for every resulting fragment.

Use overlap when necessary.

Never generate bridging language.


## 16. CHUNK OVERLAP

Overlap is required to protect context near chunk boundaries.

But overlap must contain EXACT source text.

Do not create summaries as overlap.

Example:

Chunk 10:

    paragraph 20
    paragraph 21
    paragraph 22


Chunk 11:

    paragraph 22
    paragraph 23
    paragraph 24


This is acceptable.

Store metadata indicating which content is overlapping so duplicated extraction
results can later be reconciled by source position.


## 17. DO NOT CONFUSE TEXT SPLIT "PAGES" WITH PDF PAGES

Azure AI Search Text Split terminology can use "pages" to describe text chunks.

Do NOT assume that these are physical PDF pages.

Always keep a separate explicit field for physical PDF provenance:

    source_page_number

and another field for logical/search chunk ordering:

    chunk_order


Do not overload these concepts.


## 18. REQUIRED AZURE AI SEARCH INDEX FIELDS

At minimum, maintain fields equivalent to:

document_id
document_version
document_name

chunk_id
chunk_order

content
content_vector

section_id
section_title

first_page
last_page

source_fragments

previous_chunk_id
next_chunk_id

parent_element_ids

content_hash


Where supported by the storage model also preserve:

source offsets
bounding regions
paragraph IDs
table IDs
article numbers
clause numbers


The exact schema may be adapted to Azure AI Search supported field types,
but the information MUST remain recoverable.


## 19. STABLE CHUNK IDENTIFIERS

Chunk IDs must not be random UUIDs if deterministic reprocessing is desired.

Generate stable identifiers from deterministic attributes such as:

    document_id
    document_version
    logical_order

Example:

    DOC123-C000001
    DOC123-C000002


This assists:

- repeatability
- incremental processing
- diffing
- policy lineage
- re-extraction
- contradiction analysis


## 20. STORE PREVIOUS AND NEXT RELATIONSHIPS

Each indexed chunk should know its neighbors.

Example:

{
    "chunk_id": "DOC123-C000025",
    "previous_chunk_id": "DOC123-C000024",
    "next_chunk_id": "DOC123-C000026"
}


This is important for later contextual expansion.


## 21. EXTRACTION MUST PROCESS ALL CHUNKS

When policy extraction is requested for a document:

DO NOT perform a semantic search.

Instead:

1. Filter all chunks using document_id.
2. Retrieve the complete set.
3. Sort by chunk_order.
4. Validate continuity.
5. Ensure there are no unexplained gaps.
6. Build extraction windows.
7. Process all windows.


Pseudo-code:

chunks = search(
    filter = "document_id eq '<id>'",
    select = required_fields,
    order_by = "chunk_order asc"
)

assert_complete_sequence(chunks)

for window in build_windows(chunks):
    extract_policy_candidates(window)


## 22. CONTEXT WINDOW ASSEMBLY

Do not send each embedding chunk independently to the policy LLM.

For each primary chunk create a CONTEXT WINDOW.

Conceptually:

    previous chunk
    +
    PRIMARY chunk
    +
    next chunk


or:

    previous logical block(s)
    +
    PRIMARY logical block(s)
    +
    next logical block(s)


This prevents boundaries from hiding conditions and exceptions.


Example:

Chunk 100 ends:

    An employee may receive the allowance,


Chunk 101 begins:

    provided that the employee has completed five years of service.


Sending Chunk 100 alone is unacceptable.

The extraction window should contain both.


## 23. PRIMARY REGION VS CONTEXT REGION

To prevent duplicate extraction, tell the extractor which region it owns.

Example:

<context_before>
...
</context_before>

<primary_source>
...
</primary_source>

<context_after>
...
</context_after>


Instruction to extraction model:

    Use context_before and context_after only to understand continuation.

    Extract a passage when any part of the qualifying passage intersects
    primary_source.

This allows complete cross-boundary policy extraction without processing the
same passage repeatedly.


## 24. EVEN BETTER: PROCESS LOGICAL BLOCK WINDOWS

Where possible do not base extraction windows directly on embedding chunks.

Instead retrieve/search-store metadata and rebuild:

    logical element N-1
    logical element N
    logical element N+1


Then pass those elements to the extractor.

Embedding chunks are optimized for SEARCH.

Logical source windows are optimized for POLICY EXTRACTION.

They are related but should not be assumed to be identical.


## 25. SOURCE POSITION IS THE IDENTITY OF AN EXTRACTION

Every extraction needs a source range.

Example:

{
    "document_id": "DOC123",
    "start_element": "E000175",
    "end_element": "E000176",
    "source_fragments": [
        {
            "page": 24,
            "start_offset": 743,
            "end_offset": 1091
        },
        {
            "page": 25,
            "start_offset": 0,
            "end_offset": 210
        }
    ]
}


Do not identify policies solely by their text.

The same text can legitimately appear more than once.


## 26. VERBATIM EXTRACTION GUARANTEE

The policy extractor must never be trusted merely because it was instructed
to be verbatim.

Enforce verbatim extraction programmatically.


For every returned policy:

    extracted_text

verify against the canonical source.


Required validation:

    exact source span exists


If:

    canonical_text.find(extracted_text) == -1

then:

    reject extraction


DO NOT:

    fuzzy-correct it
    rewrite it
    accept semantic similarity


It must be copied from the source.


## 27. IMPORTANT CROSS-PAGE VALIDATION ISSUE

A policy may span multiple physical pages.

Therefore a simple check against ONE page is insufficient.


Validate against the canonical logical source representation.

Alternatively validate each source fragment separately.


Example:

policy:
    source_fragments:
      page 31 span A
      page 32 span B


Validation should prove:

    A exists exactly on page 31

AND

    B exists exactly on page 32

AND

    the fragments are adjacent in logical document order


Never assume the policy must belong to only one page.


## 28. CANONICAL TEXT MUST BE STABLE

Choose ONE authoritative text representation for downstream exact matching.

Do not alternate between:

- PDF library text
- Document Intelligence text
- Search index text
- OCR output
- LLM-cleaned text


Pick one authoritative parser output and persist it.

Call it, for example:

    canonical_source_text


Every later extraction should be validated against that SAME representation.


Otherwise:

PDF parser says:

    non- Saudis

another component says:

    non-Saudis

and exact validation will fail even though both came from the same PDF.


## 29. DO NOT CLEAN TEXT AFTER INDEXING

Never perform uncontrolled transformations such as:

    trim internal punctuation
    change whitespace
    fix hyphenation
    normalize Unicode
    repair spelling
    replace smart quotes
    convert numbers
    convert bullets


unless the transformation is part of a deterministic canonicalization algorithm
performed BEFORE indexing and source validation.


If canonicalization is used:

    raw_source_text
    canonical_source_text

must BOTH be retained.


## 30. HYPHENATION ACROSS PDF LINES

PDFs can contain visual line-break hyphenation.

Example:

    employ-
    ment


Do not allow an LLM to decide that this means:

    employment


If canonicalization joins such text, the transformation must be:

- deterministic
- performed by code
- recorded
- reversible or source-mapped


Store:

raw fragments:
    "employ-"
    "ment"

canonical:
    "employment"

transformation:
    line_break_hyphen_join


The LLM must never perform this correction implicitly.


## 31. TABLE HANDLING

Tables are policy-rich and require special treatment.

Examples:

approval matrices
penalty schedules
benefit tiers
expense limits
delegation matrices
risk levels
retention schedules


Do NOT flatten a table into meaningless text.

Preserve:

    table identity
    table title
    headers
    rows
    cells
    page locations


For policy extraction, provide sufficient table structure for the model to
identify policy-bearing rows.


Never have the LLM invent sentences from the table.

If the row is returned as a policy candidate, return the source row/block in
its canonical table representation.


## 32. MULTI-PAGE TABLES

A table may continue across pages.

Do not create separate unrelated tables merely because a page changed.

Use:

- table structure
- column count
- column locations
- repeated headers
- table title
- continuation context

to detect continuation.


Preferred logical model:

TABLE-004
    page 72 rows 1-15
    page 73 rows 16-30
    page 74 rows 31-38


not:

TABLE-004A
TABLE-004B
TABLE-004C


If Azure Content Understanding is available in the selected architecture,
take advantage of its cross-page table capabilities rather than recreating
them unnecessarily.


## 33. NUMBERED LISTS

Preserve parent-child relationships.

Example:

Article 17

The employee shall:

    1. Perform...
    2. Maintain...
    3. Notify...


Represent:

parent:
    "The employee shall:"

children:
    item 1
    item 2
    item 3


If item 3 continues onto the next PDF page, it remains the SAME list item.

Do not restart the list simply because page number changed.


## 34. FOOTNOTES

Do not automatically discard footnotes.

A footnote may modify a policy.

Store them separately and preserve relationship to their anchor where possible.

During extraction, include relevant footnotes in surrounding context.

Do not merge footnote wording into the policy sentence.


## 35. HEADINGS

Headings generally aren't policy passages themselves, but they provide
important context.

Store them and include the active heading hierarchy as metadata/context:

    Part
    Chapter
    Section
    Article
    Subsection


Example:

{
    "heading_path": [
        "Work Relations",
        "Leave",
        "Annual Leave"
    ]
}


Do not inject heading words into extracted source text unless they literally
belong to the selected source passage.


## 36. SEARCH AI EMBEDDINGS

Continue generating embeddings for logical chunks.

Embeddings are valuable for later:

    policy retrieval
    related-policy search
    contradiction candidates
    duplicate candidates
    cross-document comparison


But retain the non-vector filterable fields necessary for exact document
enumeration.


At minimum:

    document_id must be filterable
    document_version must be filterable
    chunk_order must be retrievable/sortable as required by implementation


Do not design the index as vector-only retrieval.


## 37. SEPARATE EXTRACTION INDEX FROM POLICY INDEX IF APPROPRIATE

Strongly consider two logical indexes or two entity layers.


DOCUMENT CHUNK INDEX

Contains:

    canonical source text
    embeddings
    source metadata
    logical ordering
    source locations


POLICY INDEX

Contains:

    extracted verbatim policy passages
    policy metadata
    later canonical rule representation
    policy embedding
    provenance


Flow:

DOCUMENT INDEX
      ↓
policy extraction
      ↓
POLICY INDEX


Do not overwrite source chunks with generated policy representations.


## 38. DOCUMENT VERSIONING

Never overwrite policy provenance when a new version of a document arrives.

Store:

    document_id
    version_id
    content_hash
    ingestion_timestamp


Policies should reference the exact source version from which they were
extracted.


This later enables:

    added policy
    removed policy
    modified policy
    unchanged policy


## 39. CONTENT HASHES

Generate deterministic hashes for:

- complete source
- canonical source
- logical element
- chunk
- extracted passage


Example:

    SHA-256


This allows the system to prove when source content is unchanged and avoid
unnecessary reprocessing.


## 40. COVERAGE CONTROL

After extraction, the system must be able to prove that every region of the
document was considered.

Maintain processing records such as:

{
    "document_id": "...",
    "total_logical_elements": 847,
    "processed_logical_elements": 847,
    "failed_elements": [],
    "coverage_percent": 100
}


Do not mark extraction complete if chunks were silently omitted.


## 41. RETRY BEHAVIOR

If processing of a window fails:

DO NOT skip it.

Record:

    window_id
    element range
    error
    retry count


Retry according to configured policy.

Document extraction succeeds only after:

    every required logical region == processed

or an explicit failure state is returned.


## 42. DEDUPLICATION AFTER OVERLAP

Overlap will intentionally cause some policies to be seen more than once.

Do NOT deduplicate based solely on text similarity.

Deduplicate based on source identity:

    document_id
    version_id
    source start position
    source end position


Two identical sentences in different source locations must remain distinct.


## 43. POLICY EXTRACTION OUTPUT

The LLM should return:

{
  "policy_passages": [
    {
      "classification": "POLICY",
      "text": "<exact source text>",
      "source": {
        "document_id": "...",
        "first_page": 10,
        "last_page": 11,
        "source_fragments": [...]
      }
    }
  ]
}


Do not allow the LLM to generate source page numbers if the application already
knows them.

The application should attach authoritative provenance whenever possible.


## 44. PREFER APPLICATION-GENERATED METADATA

Do not ask the LLM to infer:

    page number
    source offset
    chunk ID
    document ID
    version ID


These are deterministic application facts.

The application must supply or calculate them.

The LLM should primarily decide:

    does this source passage qualify as policy-bearing?


The application handles:

    where did it come from?


## 45. POLICY EXTRACTION SHOULD NOT DEPEND ON EMBEDDING SIMILARITY

For the initial extraction workflow:

    embedding similarity score MUST NOT determine whether text gets processed.

A paragraph with low similarity to the word "policy" can still contain a
critical requirement.

Example:

    "Claims received later than thirty days shall not be considered."

This may not rank highly for generic policy queries but is clearly a rule.


Therefore:

    FULL DOCUMENT SCAN is mandatory.


## 46. CONTRADICTION ANALYSIS IS DIFFERENT

After policies have already been extracted, embeddings ARE useful.

Example:

Policy A embedding
       ↓
retrieve semantically related policies
       ↓
SOL contradiction analysis


This reduces N² comparison costs.

Do not confuse this optimization with the initial extraction stage.


## 47. QUALITY TEST: CROSS-PAGE POLICIES

Create automated tests specifically for page boundaries.

Test case:

Page 1:

    Requests exceeding SAR 50,000 require


Page 2:

    approval from the Chief Financial Officer.


Expected extracted source:

    Requests exceeding SAR 50,000 require
    approval from the Chief Financial Officer.


No words added.

No words missing.


## 48. QUALITY TEST: EXCEPTION ON NEXT PAGE

Page 20:

    Employees are entitled to reimbursement for approved travel.


Page 21:

    This does not apply when transportation is provided directly by the
    company.


Both passages must reach the same policy extraction context window.

The extractor must not see page 20 in isolation.


## 49. QUALITY TEST: LIST ACROSS PAGES

Page 31:

    Approval requires:
    1. Budget availability.
    2. Manager approval.


Page 32:

    3. Compliance approval.


The logical list must remain:

    Approval requires:
    1. Budget availability.
    2. Manager approval.
    3. Compliance approval.


without LLM reconstruction.


## 50. QUALITY TEST: TABLE ACROSS PAGES

Create a test approval matrix where:

page 1 contains:
    SAR 0-10K
    SAR 10K-50K

page 2 contains:
    SAR 50K-100K
    > SAR 100K


The ingestion pipeline must preserve the table as one logical table or clearly
linked continuation.

No row may lose its header context.


## 51. QUALITY TEST: EXACT SOURCE VALIDATION

Introduce text such as:

    The non- Saudi worker may not...


If the LLM returns:

    The non-Saudi worker may not...


validation MUST fail.

Semantic equivalence is irrelevant.

The returned policy text changed.


## 52. QUALITY TEST: EXHAUSTIVE COVERAGE

Create a synthetic 100-page policy PDF.

Place policy-bearing statements on:

    page 1
    page 19
    page 50
    page 73
    page 100


All five must be found.

The implementation must NOT rely on top-K retrieval.


## 53. QUALITY TEST: DETERMINISM

Run the exact same document through the extraction pipeline repeatedly.

Given:

    same file
    same canonical parser version
    same prompt
    same model configuration

the set of source policy passages should remain materially identical.


Compare using source spans rather than generated IDs alone.


## 54. IMPORTANT IMPLEMENTATION CONSTRAINT

DO NOT solve page continuation by increasing chunk size to something huge.

That hides the problem rather than fixing it.

Correct solution:

    reconstruct logical structure
    +
    preserve adjacent context
    +
    overlap
    +
    source mapping


not:

    put the entire 200-page PDF into one prompt.


## 55. ARCHITECTURAL INVARIANTS

The implementation is NOT complete unless all of these invariants hold:


INVARIANT 1

Every physical page is ingested.


INVARIANT 2

Every logical source element belongs to an ordered document sequence.


INVARIANT 3

Physical page boundaries do not automatically cause semantic boundaries.


INVARIANT 4

Every embedding chunk maps back to exact source locations.


INVARIANT 5

Every policy passage maps back to exact source locations.


INVARIANT 6

No LLM-generated word can enter the verbatim policy text field.


INVARIANT 7

Every extraction returned by the LLM is validated against canonical source
text.


INVARIANT 8

Every document element is processed during exhaustive policy extraction.


INVARIANT 9

Failures cannot silently reduce document coverage.


INVARIANT 10

Embedding retrieval is never used as a substitute for complete document
enumeration during policy extraction.


## 56. IMPLEMENTATION PRIORITY

When modifying the existing codebase, proceed in this order:

1. Inspect the current PDF ingestion pipeline.
2. Inspect the current Azure AI Search index schema.
3. Determine how current chunks are created.
4. Determine whether physical pages are currently treated as chunks.
5. Determine whether page/offset provenance is retained.
6. Determine whether tables/lists/paragraphs are structurally retained.
7. Identify where content can currently be lost.
8. Design the canonical document representation.
9. Implement cross-page logical reconstruction.
10. Implement deterministic chunk ordering.
11. Implement source fragment mapping.
12. Modify Search AI schema where necessary.
13. Implement full-document enumeration.
14. Implement context-window assembly.
15. Integrate the strict verbatim policy extractor.
16. Implement exact-source validation.
17. Implement document coverage validation.
18. Add boundary-focused automated tests.
19. Only then optimize performance.


## 57. DO NOT MAKE BLIND REWRITES

Before changing code:

READ the current architecture.

Trace:

    file upload
        →
    blob
        →
    parser
        →
    skillset/indexer
        →
    chunker
        →
    embedding
        →
    Search AI index
        →
    application retrieval
        →
    LLM extraction


Identify the exact component responsible for each transformation.

Do not duplicate existing functionality unnecessarily.

If the existing Azure AI Search pipeline already preserves structural
information, extend it instead of replacing it.


## 58. SMALL BUG / ARCHITECTURAL PROBLEM RULE

If you encounter an issue that appears small, such as:

    one policy getting cut at a page boundary
    a repeated table header
    a duplicate extraction
    missing page number
    a sentence beginning mid-way through a chunk

DO NOT immediately patch only that example.

Determine whether it reveals an architectural problem.

Ask:

    Is the same failure possible throughout every document?

If YES:

fix the architecture rather than special-casing the example.


## 59. FINAL DESIGN PRINCIPLE

SEARCH CHUNKS ARE NOT THE SOURCE OF TRUTH.

THE DOCUMENT IS THE SOURCE OF TRUTH.

Azure AI Search is an index over that source.

Embeddings are representations of that source.

The LLM is a classifier over that source.

None of these components is allowed to rewrite the authoritative policy text.

For policy extraction:

    UNDERSTAND SEMANTICALLY.
    SELECT STRUCTURALLY.
    COPY VERBATIM.
    VERIFY PROGRAMMATICALLY.
    PRESERVE PROVENANCE.
    PROCESS THE ENTIRE DOCUMENT.

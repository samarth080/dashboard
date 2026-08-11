# M2: Research Engine — Design

Date: 2026-08-11
Status: Implemented

## Purpose

Turn public-source documents into traceable, ranked research topics and evidence
packs. M2 establishes the source, normalization, deduplication, ranking, and
provenance contracts that later content generation must consume.

The engine must never turn an unattributed model summary into a fact. Raw source
content, derived topics, claims, and supporting excerpts remain separate and
linked throughout the workflow.

## Success criteria

- `ContentSource` is a provider-neutral async protocol.
- RSS/Atom is the first adapter and can be tested from fixture XML without a
  network connection.
- Normalized documents retain source, canonical URL, original URL, author,
  published/retrieved times, content hash, raw metadata, and credibility.
- Canonical URL matches and exact content hashes deduplicate deterministically;
  near-duplicate text uses a configurable token-similarity threshold.
- The first embedding column enables pgvector through migration
  `0003_research_engine`, while remaining nullable and provider-neutral.
- Topic candidates persist all required component scores, per-platform fit,
  the scoring configuration/version used, and a reproducible total.
- Evidence packs contain explicit claims and source excerpts linked back to raw
  documents.
- Research APIs expose sources, documents, scoring configurations, topics, and
  evidence packs.
- The Research page can inspect the current corpus and ranked topic queue.
- Unit, integration, migration-drift, lint, type, and web-build checks pass.

## Boundaries

- M2 reads configured public feeds; it does not scrape authenticated pages or
  bypass access controls.
- No LinkedIn or X API is used. M7 remains capability-gated.
- No generated claim is considered verified merely because a model produced
  it. Evidence sources must be explicit.
- No autonomous polling loop or schedule is introduced; orchestration belongs
  to M8.
- Embeddings are optional. Deterministic URL/hash/token deduplication works
  without credentials or a model.

## Source abstraction

`ContentSource.fetch()` returns normalized `SourceDocument` values and never
persists. An adapter owns retrieval and source-specific parsing; the ingestion
service owns canonicalization, hashing, deduplication, and transactions.

The first adapter parses RSS 2.x and Atom feeds with the standard library. Its
parser accepts XML directly for deterministic tests. Network fetching accepts
only HTTP(S) public destinations, applies response-size and timeout limits, and
rejects loopback, private, link-local, multicast, and reserved IP addresses.

`ResearchSource` stores the adapter kind, feed URL, enabled state, default
credibility, and adapter configuration. Secrets do not belong in this JSON.

## Data model

### Documents

`RawDocument` stores the immutable normalized payload:

- source and optional source-native identifier;
- original and canonical URL;
- title, author, content, language;
- published and retrieved timestamps;
- SHA-256 content hash;
- source credibility and raw metadata;
- optional `duplicate_of_id` for near-duplicates; and
- optional unconstrained pgvector `embedding` plus `embedding_model`.

Canonical URL is unique. Exact content matches return the existing canonical
document. Near-duplicates are retained for provenance but point to the selected
canonical document and are excluded from default topic inputs.

### Ranking

`ScoringConfig` stores a versioned JSON weight map and near-duplicate threshold.
Exactly one active configuration is selected by default; callers may request a
specific configuration for reproducibility.

`TopicCandidate` persists normalized component scores for freshness, relevance,
novelty, momentum, credibility, authority fit, insight potential, LinkedIn fit,
and X fit. `total_score` is the weighted mean of the first seven dimensions plus
the mean platform fit. Every component is in `[0, 1]`; all arithmetic uses
`Decimal`.

Weights are validated against the exact component key set, non-negative, and
must have a positive sum. No ranking weight is embedded in scorer code.

`TopicDocument` is the many-to-many link between topics and source documents.

### Evidence

`EvidencePack` belongs one-to-one with a topic and records a thesis.
`Claim` belongs to a pack and stores its statement, confidence, and verification
status. `EvidenceSource` belongs to a claim, references a raw document, and
stores the supporting excerpt and optional locator. A claim is only
`supported` when at least one evidence source exists; the service enforces this
transition.

## Deduplication

1. Canonicalize HTTP(S) URLs: lower-case scheme/host, remove fragments and
   default ports, normalize path, sort query parameters, and drop configured
   tracking parameters.
2. Match the canonical URL.
3. Match the exact SHA-256 hash of normalized text.
4. Compare word-shingle Jaccard similarity against canonical documents using
   the active configuration threshold.
5. Persist novel documents; retain near-duplicates with `duplicate_of_id`.

This bounded deterministic path is the credential-free baseline. Vector
similarity can be added once an embedding provider is configured, without
changing the ingestion contract.

## API

- `GET|POST /api/research/sources`
- `PATCH /api/research/sources/{source_id}`
- `POST /api/research/sources/{source_id}/refresh`
- `GET|POST /api/research/documents`
- `GET /api/research/documents/{document_id}`
- `GET|POST /api/research/scoring-configs`
- `POST /api/research/extract`
- `GET|POST /api/research/topics`
- `GET /api/research/topics/{topic_id}`
- `POST /api/research/topics/{topic_id}/rescore`
- `GET|PUT /api/research/topics/{topic_id}/evidence`

The manual document endpoint exists for user-provided or fixture-backed content;
it runs through the same normalization and deduplication service as adapters.

## pgvector decision

Migration `0003` runs `CREATE EXTENSION IF NOT EXISTS vector` before creating
the first vector column. The SQLAlchemy model uses the official
`pgvector.sqlalchemy.VECTOR` type. The column is unconstrained because no real
embedding provider/model has been selected; `embedding_model` identifies the
vector space and future similarity queries must compare like with like.

No approximate index is created yet. Corpus size and query patterns should
justify HNSW/IVFFlat parameters rather than guessing them up front.

## Testing

- URL canonicalization, hashing, RSS/Atom parsing, unsafe-host rejection, token
  similarity, scoring validation, and total-score reproducibility are unit
  tested.
- Integration tests cover migrations, extension presence, document ingestion
  and deduplication, topic ranking, evidence invariants, and the HTTP workflow.
- Tests use fixture XML and local values; they do not depend on live feeds.

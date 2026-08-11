"use client";

import { FormEvent, useEffect, useState } from "react";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

interface Source {
  id: string;
  key: string;
  name: string;
  url: string;
  enabled: boolean;
  default_credibility: string;
  last_retrieved_at: string | null;
}

interface Document {
  id: string;
  source_id: string | null;
  canonical_url: string;
  title: string;
  author: string | null;
  content: string;
  credibility: string;
  duplicate_of_id: string | null;
  published_at: string | null;
}

interface Topic {
  id: string;
  title: string;
  summary: string;
  status: string;
  total_score: string;
  platform_fit: { linkedin: string; x: string };
  document_ids: string[];
  scoring_config_id: string;
}

interface EvidenceSource {
  id: string;
  document_id: string;
  excerpt: string;
  locator: string | null;
  supports: boolean;
}

interface EvidencePack {
  id: string;
  thesis: string;
  claims: Array<{
    id: string;
    statement: string;
    confidence: string;
    verification_status: string;
    sources: EvidenceSource[];
  }>;
}

interface ApiError {
  detail?: string;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
  });
  if (!response.ok) {
    const body = (await response.json().catch(() => ({}))) as ApiError;
    throw new Error(body.detail ?? `Request failed (${response.status})`);
  }
  return (await response.json()) as T;
}

async function requestOptional<T>(path: string): Promise<T | null> {
  const response = await fetch(`${API_URL}${path}`);
  if (response.status === 404) return null;
  if (!response.ok) {
    const body = (await response.json().catch(() => ({}))) as ApiError;
    throw new Error(body.detail ?? `Request failed (${response.status})`);
  }
  return (await response.json()) as T;
}

export default function ResearchPage() {
  const [sources, setSources] = useState<Source[]>([]);
  const [documents, setDocuments] = useState<Document[]>([]);
  const [topics, setTopics] = useState<Topic[]>([]);
  const [sourceForm, setSourceForm] = useState({
    key: "",
    name: "",
    url: "",
    credibility: "0.500",
  });
  const [documentForm, setDocumentForm] = useState({
    url: "",
    title: "",
    content: "",
    credibility: "0.500",
  });
  const [topicForm, setTopicForm] = useState({
    title: "",
    summary: "",
    document_id: "",
    freshness: "0.700",
    relevance: "0.800",
    novelty: "0.700",
    momentum: "0.500",
    credibility: "0.700",
    authority_fit: "0.700",
    insight_potential: "0.800",
    linkedin_fit: "0.800",
    x_fit: "0.700",
  });
  const [selectedTopic, setSelectedTopic] = useState<Topic | null>(null);
  const [evidence, setEvidence] = useState<EvidencePack | null>(null);
  const [evidenceForm, setEvidenceForm] = useState({
    thesis: "",
    statement: "",
    confidence: "0.700",
    document_id: "",
    excerpt: "",
    locator: "",
  });
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("Loading research workspace…");
  const [error, setError] = useState<string | null>(null);

  async function load() {
    setError(null);
    try {
      const [loadedSources, loadedDocuments, loadedTopics] = await Promise.all([
        request<Source[]>("/api/research/sources"),
        request<Document[]>("/api/research/documents?include_duplicates=true"),
        request<Topic[]>("/api/research/topics"),
      ]);
      setSources(loadedSources);
      setDocuments(loadedDocuments);
      setTopics(loadedTopics);
      setNotice("Research workspace loaded.");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
      setNotice("");
    }
  }

  useEffect(() => {
    void load();
  }, []);

  async function runAction(action: () => Promise<void | string>, success: string) {
    setBusy(true);
    setError(null);
    try {
      const detail = await action();
      setNotice(detail ?? success);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setBusy(false);
    }
  }

  function addSource(event: FormEvent) {
    event.preventDefault();
    void runAction(async () => {
      const created = await request<Source>("/api/research/sources", {
        method: "POST",
        body: JSON.stringify({
          key: sourceForm.key,
          name: sourceForm.name,
          url: sourceForm.url,
          default_credibility: sourceForm.credibility,
        }),
      });
      setSources((current) => [...current, created].sort((a, b) => a.name.localeCompare(b.name)));
      setSourceForm({ key: "", name: "", url: "", credibility: "0.500" });
    }, "Source registered. Refresh it when you are ready to make a public feed request.");
  }

  function refreshSource(source: Source) {
    void runAction(async () => {
      const result = await request<{ fetched: number; created: number; duplicates: number }>(
        `/api/research/sources/${source.id}/refresh`,
        { method: "POST" },
      );
      await load();
      return (
        `${source.name}: fetched ${result.fetched}, created ${result.created}, ` +
        `${result.duplicates} duplicate(s).`
      );
    }, "Source refreshed.");
  }

  function addDocument(event: FormEvent) {
    event.preventDefault();
    void runAction(async () => {
      const result = await request<{ document: Document; outcome: string }>(
        "/api/research/documents",
        {
          method: "POST",
          body: JSON.stringify({
            url: documentForm.url,
            title: documentForm.title,
            content: documentForm.content,
            credibility: documentForm.credibility,
          }),
        },
      );
      setDocuments((current) => {
        if (current.some((document) => document.id === result.document.id)) return current;
        return [result.document, ...current];
      });
      setDocumentForm({ url: "", title: "", content: "", credibility: "0.500" });
      return `Document result: ${result.outcome.replaceAll("_", " ")}.`;
    }, "Document ingested.");
  }

  function addTopic(event: FormEvent) {
    event.preventDefault();
    void runAction(async () => {
      const created = await request<Topic>("/api/research/topics", {
        method: "POST",
        body: JSON.stringify({
          title: topicForm.title,
          summary: topicForm.summary,
          document_ids: [topicForm.document_id],
          scores: {
            freshness: topicForm.freshness,
            relevance: topicForm.relevance,
            novelty: topicForm.novelty,
            momentum: topicForm.momentum,
            credibility: topicForm.credibility,
            authority_fit: topicForm.authority_fit,
            insight_potential: topicForm.insight_potential,
            platform_fit: { linkedin: topicForm.linkedin_fit, x: topicForm.x_fit },
          },
        }),
      });
      setTopics((current) =>
        [...current, created].sort((a, b) => Number(b.total_score) - Number(a.total_score)),
      );
      setTopicForm((current) => ({ ...current, title: "", summary: "" }));
    }, "Topic scored with the active database configuration.");
  }

  function extractTopics() {
    void runAction(async () => {
      const extracted = await request<Topic[]>("/api/research/extract", {
        method: "POST",
        body: JSON.stringify({
          document_ids: canonicalDocuments.slice(0, 20).map((document) => document.id),
        }),
      });
      setTopics((current) =>
        [...current, ...extracted].sort(
          (a, b) => Number(b.total_score) - Number(a.total_score),
        ),
      );
      return (
        extracted.length > 0
          ? `Extracted ${extracted.length} clustered topic(s).`
          : "The model recommended no topics for this corpus."
      );
    }, "Topic extraction complete.");
  }

  function inspectTopic(topic: Topic) {
    setSelectedTopic(topic);
    setEvidenceForm((current) => ({
      ...current,
      document_id: topic.document_ids[0] ?? "",
    }));
    void runAction(async () => {
      const pack = await requestOptional<EvidencePack>(
        `/api/research/topics/${topic.id}/evidence`,
      );
      setEvidence(pack);
    }, `Inspecting ${topic.title}.`);
  }

  function saveEvidence(event: FormEvent) {
    event.preventDefault();
    if (!selectedTopic) return;
    void runAction(async () => {
      const pack = await request<EvidencePack>(
        `/api/research/topics/${selectedTopic.id}/evidence`,
        {
          method: "PUT",
          body: JSON.stringify({
            thesis: evidenceForm.thesis,
            claims: [
              {
                statement: evidenceForm.statement,
                confidence: evidenceForm.confidence,
                verification_status: "supported",
                sources: [
                  {
                    document_id: evidenceForm.document_id,
                    excerpt: evidenceForm.excerpt,
                    locator: evidenceForm.locator || null,
                    supports: true,
                  },
                ],
              },
            ],
          }),
        },
      );
      setEvidence(pack);
    }, "Evidence pack saved with document provenance.");
  }

  const canonicalDocuments = documents.filter((document) => !document.duplicate_of_id);

  return (
    <div style={{ maxWidth: 1120, margin: "0 auto", fontFamily: "system-ui, sans-serif" }}>
      <header style={{ marginBottom: 24 }}>
        <p style={{ color: "#6b7280", marginBottom: 4 }}>M2 · Research Engine</p>
        <h1 style={{ margin: 0 }}>Research workspace</h1>
        <p style={{ color: "#4b5563" }}>
          Normalize public documents, remove duplicates, rank topic candidates, and keep every
          claim attached to evidence.
        </p>
        {notice && <p style={{ color: "#166534" }}>{notice}</p>}
        {error && <p style={{ color: "#b91c1c" }}>{error}</p>}
      </header>

      <div style={metricGrid}>
        <Metric label="Sources" value={sources.length} />
        <Metric label="Canonical documents" value={canonicalDocuments.length} />
        <Metric label="Near duplicates" value={documents.length - canonicalDocuments.length} />
        <Metric label="Ranked topics" value={topics.length} />
      </div>

      <Section title="Public feed sources" description="Only public HTTP(S) RSS/Atom feeds.">
        <form onSubmit={addSource} style={formGrid}>
          <Field label="Stable key">
            <input
              pattern="[a-z0-9][a-z0-9_-]*"
              required
              value={sourceForm.key}
              onChange={(event) => setSourceForm({ ...sourceForm, key: event.target.value })}
            />
          </Field>
          <Field label="Name">
            <input
              required
              value={sourceForm.name}
              onChange={(event) => setSourceForm({ ...sourceForm, name: event.target.value })}
            />
          </Field>
          <Field label="Feed URL">
            <input
              required
              type="url"
              value={sourceForm.url}
              onChange={(event) => setSourceForm({ ...sourceForm, url: event.target.value })}
            />
          </Field>
          <Field label="Credibility (0–1)">
            <input
              max="1"
              min="0"
              step="0.05"
              type="number"
              value={sourceForm.credibility}
              onChange={(event) =>
                setSourceForm({ ...sourceForm, credibility: event.target.value })
              }
            />
          </Field>
          <button disabled={busy} type="submit">
            Register source
          </button>
        </form>
        <div style={listGrid}>
          {sources.map((source) => (
            <div key={source.id} style={cardStyle}>
              <div>
                <strong>{source.name}</strong>
                <p style={muted}>{source.url}</p>
                <small>Credibility {source.default_credibility}</small>
              </div>
              <button disabled={busy || !source.enabled} onClick={() => refreshSource(source)}>
                Refresh
              </button>
            </div>
          ))}
        </div>
      </Section>

      <Section
        title="Document corpus"
        description="Manual ingestion uses the same canonicalization and deduplication path."
      >
        <form onSubmit={addDocument} style={formGrid}>
          <Field label="Public URL">
            <input
              required
              type="url"
              value={documentForm.url}
              onChange={(event) => setDocumentForm({ ...documentForm, url: event.target.value })}
            />
          </Field>
          <Field label="Title">
            <input
              required
              value={documentForm.title}
              onChange={(event) => setDocumentForm({ ...documentForm, title: event.target.value })}
            />
          </Field>
          <Field label="Credibility (0–1)">
            <input
              max="1"
              min="0"
              step="0.05"
              type="number"
              value={documentForm.credibility}
              onChange={(event) =>
                setDocumentForm({ ...documentForm, credibility: event.target.value })
              }
            />
          </Field>
          <Field label="Normalized content" wide>
            <textarea
              minLength={20}
              required
              rows={6}
              value={documentForm.content}
              onChange={(event) =>
                setDocumentForm({ ...documentForm, content: event.target.value })
              }
            />
          </Field>
          <button disabled={busy} type="submit">
            Ingest document
          </button>
        </form>
        <div style={listGrid}>
          {documents.map((document) => (
            <article key={document.id} style={cardStyle}>
              <div>
                <strong>{document.title}</strong>
                <p style={muted}>{document.canonical_url}</p>
                <small>
                  Credibility {document.credibility}
                  {document.duplicate_of_id ? " · near duplicate" : " · canonical"}
                </small>
              </div>
            </article>
          ))}
        </div>
      </Section>

      <Section
        title="Ranked topic queue"
        description="Every component score is explicit; weights come from the active DB config."
      >
        <div style={{ marginBottom: 18 }}>
          <button
            disabled={busy || canonicalDocuments.length === 0}
            type="button"
            onClick={extractTopics}
          >
            Extract and cluster from corpus
          </button>
          <small style={{ ...muted, marginLeft: 10 }}>
            Uses at most 20 canonical documents and the versioned extraction prompt.
          </small>
        </div>
        <form onSubmit={addTopic} style={formGrid}>
          <Field label="Topic title">
            <input
              required
              value={topicForm.title}
              onChange={(event) => setTopicForm({ ...topicForm, title: event.target.value })}
            />
          </Field>
          <Field label="Source document">
            <select
              required
              value={topicForm.document_id}
              onChange={(event) => setTopicForm({ ...topicForm, document_id: event.target.value })}
            >
              <option value="">Select a canonical document</option>
              {canonicalDocuments.map((document) => (
                <option key={document.id} value={document.id}>
                  {document.title}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Summary" wide>
            <textarea
              required
              rows={3}
              value={topicForm.summary}
              onChange={(event) => setTopicForm({ ...topicForm, summary: event.target.value })}
            />
          </Field>
          {(
            [
              "freshness",
              "relevance",
              "novelty",
              "momentum",
              "credibility",
              "authority_fit",
              "insight_potential",
              "linkedin_fit",
              "x_fit",
            ] as const
          ).map((key) => (
            <Field key={key} label={key.replaceAll("_", " ")}>
              <input
                max="1"
                min="0"
                step="0.05"
                type="number"
                value={topicForm[key]}
                onChange={(event) => setTopicForm({ ...topicForm, [key]: event.target.value })}
              />
            </Field>
          ))}
          <button disabled={busy || canonicalDocuments.length === 0} type="submit">
            Score topic
          </button>
        </form>
        <div style={listGrid}>
          {topics.map((topic, index) => (
            <article key={topic.id} style={cardStyle}>
              <div>
                <small>#{index + 1} · {topic.status}</small>
                <h3 style={{ margin: "4px 0" }}>{topic.title}</h3>
                <p style={muted}>{topic.summary}</p>
                <strong>Score {topic.total_score}</strong>
                <small style={{ marginLeft: 8 }}>
                  LinkedIn {topic.platform_fit.linkedin} · X {topic.platform_fit.x}
                </small>
              </div>
              <button disabled={busy} onClick={() => inspectTopic(topic)}>
                Evidence
              </button>
            </article>
          ))}
        </div>
      </Section>

      {selectedTopic && (
        <Section
          title={`Evidence · ${selectedTopic.title}`}
          description="A supported claim must cite a document already linked to this topic."
        >
          {evidence && (
            <div style={{ ...cardStyle, display: "block", marginBottom: 16 }}>
              <strong>{evidence.thesis}</strong>
              {evidence.claims.map((claim) => (
                <div key={claim.id} style={{ marginTop: 12 }}>
                  <p>{claim.statement}</p>
                  <small>
                    {claim.verification_status} · confidence {claim.confidence} · {" "}
                    {claim.sources.length} source(s)
                  </small>
                </div>
              ))}
            </div>
          )}
          <form onSubmit={saveEvidence} style={formGrid}>
            <Field label="Thesis" wide>
              <textarea
                required
                rows={2}
                value={evidenceForm.thesis}
                onChange={(event) =>
                  setEvidenceForm({ ...evidenceForm, thesis: event.target.value })
                }
              />
            </Field>
            <Field label="Supported claim" wide>
              <textarea
                required
                rows={2}
                value={evidenceForm.statement}
                onChange={(event) =>
                  setEvidenceForm({ ...evidenceForm, statement: event.target.value })
                }
              />
            </Field>
            <Field label="Linked document">
              <select
                required
                value={evidenceForm.document_id}
                onChange={(event) =>
                  setEvidenceForm({ ...evidenceForm, document_id: event.target.value })
                }
              >
                {selectedTopic.document_ids.map((documentId) => (
                  <option key={documentId} value={documentId}>
                    {documents.find((document) => document.id === documentId)?.title ?? documentId}
                  </option>
                ))}
              </select>
            </Field>
            <Field label="Confidence">
              <input
                max="1"
                min="0"
                step="0.05"
                type="number"
                value={evidenceForm.confidence}
                onChange={(event) =>
                  setEvidenceForm({ ...evidenceForm, confidence: event.target.value })
                }
              />
            </Field>
            <Field label="Exact supporting excerpt" wide>
              <textarea
                minLength={10}
                required
                rows={4}
                value={evidenceForm.excerpt}
                onChange={(event) =>
                  setEvidenceForm({ ...evidenceForm, excerpt: event.target.value })
                }
              />
            </Field>
            <Field label="Locator">
              <input
                placeholder="paragraph, section, timestamp…"
                value={evidenceForm.locator}
                onChange={(event) =>
                  setEvidenceForm({ ...evidenceForm, locator: event.target.value })
                }
              />
            </Field>
            <button disabled={busy} type="submit">
              Save evidence pack
            </button>
          </form>
        </Section>
      )}
    </div>
  );
}

function Metric({ label, value }: { label: string; value: number }) {
  return (
    <div style={{ ...cardStyle, display: "block" }}>
      <strong style={{ fontSize: 28 }}>{value}</strong>
      <div style={muted}>{label}</div>
    </div>
  );
}

function Section({
  title,
  description,
  children,
}: {
  title: string;
  description: string;
  children: React.ReactNode;
}) {
  return (
    <section style={{ borderTop: "1px solid #e5e7eb", padding: "28px 0" }}>
      <h2 style={{ marginBottom: 4 }}>{title}</h2>
      <p style={{ ...muted, marginTop: 0 }}>{description}</p>
      {children}
    </section>
  );
}

function Field({
  label,
  wide = false,
  children,
}: {
  label: string;
  wide?: boolean;
  children: React.ReactNode;
}) {
  return (
    <label style={{ display: "grid", gap: 6, gridColumn: wide ? "1 / -1" : undefined }}>
      <span style={{ fontSize: 14, fontWeight: 600, textTransform: "capitalize" }}>{label}</span>
      {children}
    </label>
  );
}

const metricGrid = {
  display: "grid",
  gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))",
  gap: 12,
  marginBottom: 24,
};

const formGrid = {
  display: "grid",
  gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))",
  gap: 14,
  alignItems: "end",
};

const listGrid = { display: "grid", gap: 10, marginTop: 18 };

const cardStyle = {
  border: "1px solid #e5e7eb",
  borderRadius: 10,
  padding: 14,
  display: "flex",
  alignItems: "center",
  justifyContent: "space-between",
  gap: 16,
};

const muted = { color: "#6b7280" };

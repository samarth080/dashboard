"use client";

import { FormEvent, ReactNode, useEffect, useMemo, useState } from "react";

import { DuplicatePanel, DuplicatePreview } from "./DuplicatePanel";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

const ANGLE_TYPES = [
  "framework",
  "technical",
  "product",
  "business",
  "career",
  "contrarian",
  "tutorial",
  "breakdown",
  "prediction",
  "case_study",
  "comparison",
] as const;

const STAGE_ORDER = [
  "angle",
  "outline",
  "draft",
  "voice_transform",
  "fact_check",
  "quality_evaluation",
  "rewrite",
  "linkedin_adaptation",
  "x_adaptation",
] as const;

const EDITABLE_STAGES = new Set([
  "angle",
  "outline",
  "draft",
  "voice_transform",
  "rewrite",
  "linkedin_adaptation",
  "x_adaptation",
]);

interface Topic {
  id: string;
  title: string;
  summary: string;
  status: string;
  total_score: string;
}

interface EvidenceClaim {
  id: string;
  statement: string;
  verification_status: string;
  sources: Array<{ id: string; excerpt: string; supports: boolean }>;
}

interface EvidencePack {
  id: string;
  topic_id: string;
  thesis: string;
  claims: EvidenceClaim[];
}

interface ClaimReference {
  id: string;
  claimed_claim_id: string;
  resolved_claim_id: string | null;
  statement: string;
}

interface Artifact {
  id: string;
  stage: string;
  revision: number;
  content: string;
  structured_data: Record<string, unknown>;
  source: string;
  prompt_version: string | null;
  model: string | null;
  run_id: string | null;
  claim_references: ClaimReference[];
  created_at: string;
}

interface Approval {
  id: string;
  platform: "linkedin" | "x";
  decision: "pending" | "approved" | "rejected";
  required_level: number;
  actor: string | null;
  reason: string | null;
  decided_at: string | null;
}

interface Workflow {
  id: string;
  topic_id: string;
  evidence_pack_id: string;
  angle_type: string;
  requested_platforms: string[];
  current_stage: string;
  status: string;
  latest_run_id: string | null;
  artifacts: Artifact[];
  approvals: Approval[];
  created_at: string;
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

function label(value: string) {
  return value.replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function latestArtifacts(workflow: Workflow): Artifact[] {
  const latest = new Map<string, Artifact>();
  for (const artifact of workflow.artifacts) {
    const current = latest.get(artifact.stage);
    if (!current || artifact.revision > current.revision) latest.set(artifact.stage, artifact);
  }
  return STAGE_ORDER.flatMap((stage) => {
    const artifact = latest.get(stage);
    return artifact ? [artifact] : [];
  });
}

export default function ContentPage() {
  const [topics, setTopics] = useState<Topic[]>([]);
  const [workflows, setWorkflows] = useState<Workflow[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [evidence, setEvidence] = useState<EvidencePack | null>(null);
  const [form, setForm] = useState({
    topic_id: "",
    angle_type: "framework",
    linkedin: true,
    x: true,
  });
  const [editForm, setEditForm] = useState({
    stage: "",
    content: "",
    claim_id: "",
    note: "",
  });
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("Loading content workspace…");
  const [error, setError] = useState<string | null>(null);
  // Keyed by platform so a duplicate check and its override reason for
  // LinkedIn never leaks into an approval decision made for X, or vice versa.
  const [duplicatePreviews, setDuplicatePreviews] = useState<Record<string, DuplicatePreview | null>>({});
  const [overrideReasons, setOverrideReasons] = useState<Record<string, string>>({});

  const selected = useMemo(
    () => workflows.find((workflow) => workflow.id === selectedId) ?? null,
    [selectedId, workflows],
  );
  const selectedTopic = topics.find((topic) => topic.id === selected?.topic_id) ?? null;
  const supportedClaims =
    evidence?.claims.filter(
      (claim) =>
        claim.verification_status === "supported" && claim.sources.some((source) => source.supports),
    ) ?? [];

  async function load(preferredId?: string) {
    setError(null);
    try {
      const [loadedTopics, loadedWorkflows] = await Promise.all([
        request<Topic[]>("/api/research/topics"),
        request<Workflow[]>("/api/content/workflows"),
      ]);
      setTopics(loadedTopics);
      setWorkflows(loadedWorkflows);
      setForm((current) => ({
        ...current,
        topic_id: current.topic_id || loadedTopics[0]?.id || "",
      }));
      const nextId =
        preferredId ?? selectedId ?? (loadedWorkflows.length > 0 ? loadedWorkflows[0].id : null);
      setSelectedId(nextId);
      if (nextId) {
        const workflow = loadedWorkflows.find((item) => item.id === nextId);
        if (workflow) {
          setEvidence(
            await requestOptional<EvidencePack>(
              `/api/research/topics/${workflow.topic_id}/evidence`,
            ),
          );
        }
      }
      setNotice("Content workspace loaded.");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
      setNotice("");
    }
  }

  useEffect(() => {
    void load();
    // The initial load is intentional; later refreshes are explicit actions.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function runAction(action: () => Promise<string | void>, success: string) {
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

  function replaceWorkflow(updated: Workflow) {
    setWorkflows((current) => {
      const exists = current.some((workflow) => workflow.id === updated.id);
      const next = exists
        ? current.map((workflow) => (workflow.id === updated.id ? updated : workflow))
        : [updated, ...current];
      return next.sort((a, b) => b.created_at.localeCompare(a.created_at));
    });
    setSelectedId(updated.id);
  }

  function createWorkflow(event: FormEvent) {
    event.preventDefault();
    const platforms = [form.linkedin ? "linkedin" : null, form.x ? "x" : null].filter(Boolean);
    if (platforms.length === 0) {
      setError("Choose at least one platform.");
      return;
    }
    void runAction(async () => {
      const created = await request<Workflow>("/api/content/workflows", {
        method: "POST",
        body: JSON.stringify({
          topic_id: form.topic_id,
          angle_type: form.angle_type,
          platforms,
        }),
      });
      replaceWorkflow(created);
      setEvidence(
        await requestOptional<EvidencePack>(`/api/research/topics/${created.topic_id}/evidence`),
      );
      return "Workflow created. Run it when the evidence and angle are ready.";
    }, "Workflow created.");
  }

  function inspectWorkflow(workflow: Workflow) {
    setSelectedId(workflow.id);
    setEditForm({ stage: "", content: "", claim_id: "", note: "" });
    void runAction(async () => {
      setEvidence(
        await requestOptional<EvidencePack>(
          `/api/research/topics/${workflow.topic_id}/evidence`,
        ),
      );
    }, `Inspecting ${topics.find((topic) => topic.id === workflow.topic_id)?.title ?? "workflow"}.`);
  }

  function runSelected() {
    if (!selected) return;
    void runAction(async () => {
      const generated = await request<Workflow>(
        `/api/content/workflows/${selected.id}/run`,
        { method: "POST" },
      );
      replaceWorkflow(generated);
      return generated.status === "fact_check_failed"
        ? "Generation stopped at fact check. Inspect the findings before rerunning."
        : "All stages generated. Platform drafts now require explicit approval.";
    }, "Workflow generated.");
  }

  function beginEdit(artifact: Artifact) {
    const claimId = artifact.claim_references[0]?.resolved_claim_id ?? supportedClaims[0]?.id ?? "";
    setEditForm({
      stage: artifact.stage,
      content: artifact.content,
      claim_id: claimId,
      note: "",
    });
  }

  function saveRevision(event: FormEvent) {
    event.preventDefault();
    if (!selected || !editForm.stage) return;
    const claim = supportedClaims.find((item) => item.id === editForm.claim_id);
    // A cached preview describes the text that was checked. Editing a platform
    // adaptation replaces that text, so the stale verdict — and any override
    // reason typed against it — must not survive the edit.
    const editedPlatform =
      editForm.stage === "linkedin_adaptation"
        ? "linkedin"
        : editForm.stage === "x_adaptation"
          ? "x"
          : null;
    void runAction(async () => {
      const updated = await request<Workflow>(
        `/api/content/workflows/${selected.id}/artifacts/${editForm.stage}`,
        {
          method: "PUT",
          body: JSON.stringify({
            content: editForm.content,
            claims: claim ? [{ statement: claim.statement, claim_id: claim.id }] : [],
            note: editForm.note || null,
          }),
        },
      );
      replaceWorkflow(updated);
      if (editedPlatform) {
        setDuplicatePreviews((current) => ({ ...current, [editedPlatform]: null }));
        setOverrideReasons((current) => ({ ...current, [editedPlatform]: "" }));
      }
      setEditForm({ stage: "", content: "", claim_id: "", note: "" });
      return "Manual revision appended; the earlier revision remains in history.";
    }, "Revision saved.");
  }

  async function previewDuplicate(platform: "linkedin" | "x") {
    if (!selected) return;
    const adaptation = latestArtifacts(selected).find(
      (artifact) => artifact.stage === `${platform}_adaptation`,
    );
    if (!adaptation) return;
    const preview = await request<DuplicatePreview>("/api/memory/duplicate-check", {
      method: "POST",
      // Send the workflow so the preview excludes this workflow's own post
      // record, exactly as the approval gate does. Without it the panel scores
      // 1.0 against the row a previous approval wrote and shows BLOCK, while
      // the server would return `clear`.
      body: JSON.stringify({ platform, content: adaptation.content, workflow_id: selected.id }),
    });
    setDuplicatePreviews((current) => ({ ...current, [platform]: preview }));
  }

  function decide(platform: "linkedin" | "x", decision: "approved" | "rejected") {
    if (!selected) return;
    const preview = duplicatePreviews[platform] ?? null;
    const reason = (overrideReasons[platform] ?? "").trim();
    const override = preview?.verdict === "block" && reason.length > 0;
    void runAction(async () => {
      const updated = await request<Workflow>(
        `/api/content/workflows/${selected.id}/approval`,
        {
          method: "POST",
          body: JSON.stringify({
            platform,
            decision,
            actor: "user",
            reason: decision === "approved" ? "Reviewed in Content workspace." : "Needs revision.",
            duplicate_override: override,
            override_reason: override ? reason : null,
          }),
        },
      );
      replaceWorkflow(updated);
      setDuplicatePreviews((current) => ({ ...current, [platform]: null }));
      setOverrideReasons((current) => ({ ...current, [platform]: "" }));
      return `${label(platform)} draft ${decision}. No external action was performed.`;
    }, "Approval recorded.");
  }

  const stages = selected ? latestArtifacts(selected) : [];

  return (
    <div style={{ maxWidth: 1180, margin: "0 auto", fontFamily: "system-ui, sans-serif" }}>
      <header style={{ marginBottom: 24 }}>
        <p style={{ color: "#6b7280", marginBottom: 4 }}>M3 · Content Engine</p>
        <h1 style={{ margin: 0 }}>Evidence-grounded content studio</h1>
        <p style={{ color: "#4b5563", maxWidth: 820 }}>
          Build visible stage-by-stage drafts from M2 evidence, inspect fact and quality reports,
          then approve local LinkedIn and X adaptations. Approval never publishes anything.
        </p>
        {notice && <p style={{ color: "#166534" }}>{notice}</p>}
        {error && <p style={{ color: "#b91c1c" }}>{error}</p>}
      </header>

      <div style={metricGrid}>
        <Metric label="Workflows" value={workflows.length} />
        <Metric label="Ready for review" value={workflows.filter((item) => item.status === "ready_for_approval").length} />
        <Metric label="Approved locally" value={workflows.filter((item) => item.status === "approved").length} />
        <Metric label="Fact-check stops" value={workflows.filter((item) => item.status === "fact_check_failed").length} />
      </div>

      <Section
        title="Start from research"
        description="Choose a topic that already has at least one supported evidence claim."
      >
        <form onSubmit={createWorkflow} style={formGrid}>
          <Field label="Research topic">
            <select
              required
              value={form.topic_id}
              onChange={(event) => setForm({ ...form, topic_id: event.target.value })}
            >
              <option value="">Choose a topic</option>
              {topics.map((topic) => (
                <option key={topic.id} value={topic.id}>
                  {topic.title} · {Number(topic.total_score).toFixed(2)}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Angle type">
            <select
              value={form.angle_type}
              onChange={(event) => setForm({ ...form, angle_type: event.target.value })}
            >
              {ANGLE_TYPES.map((angle) => (
                <option key={angle} value={angle}>
                  {label(angle)}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Platform drafts">
            <div style={{ display: "flex", gap: 16, paddingTop: 8 }}>
              <label>
                <input
                  type="checkbox"
                  checked={form.linkedin}
                  onChange={(event) => setForm({ ...form, linkedin: event.target.checked })}
                />{" "}
                LinkedIn
              </label>
              <label>
                <input
                  type="checkbox"
                  checked={form.x}
                  onChange={(event) => setForm({ ...form, x: event.target.checked })}
                />{" "}
                X
              </label>
            </div>
          </Field>
          <button disabled={busy || !form.topic_id} type="submit" style={primaryButton}>
            Create workflow
          </button>
        </form>
      </Section>

      <div style={{ display: "grid", gridTemplateColumns: "minmax(260px, 0.8fr) minmax(0, 2fr)", gap: 20 }}>
        <Section title="Workflow queue" description="Each attempt keeps its own stage history.">
          <div style={{ display: "grid", gap: 10 }}>
            {workflows.length === 0 && <p style={muted}>No content workflows yet.</p>}
            {workflows.map((workflow) => {
              const topic = topics.find((item) => item.id === workflow.topic_id);
              return (
                <button
                  key={workflow.id}
                  onClick={() => inspectWorkflow(workflow)}
                  style={{
                    ...queueButton,
                    borderColor: selectedId === workflow.id ? "#2563eb" : "#d1d5db",
                    background: selectedId === workflow.id ? "#eff6ff" : "white",
                  }}
                >
                  <strong>{topic?.title ?? "Unknown topic"}</strong>
                  <span style={muted}>{label(workflow.angle_type)} angle</span>
                  <span style={{ color: statusColor(workflow.status) }}>{label(workflow.status)}</span>
                </button>
              );
            })}
          </div>
        </Section>

        <Section
          title={selectedTopic?.title ?? "Select a workflow"}
          description={selectedTopic?.summary ?? "Inspect its evidence and persisted stages here."}
        >
          {!selected ? (
            <p style={muted}>Choose or create a workflow to continue.</p>
          ) : (
            <div style={{ display: "grid", gap: 18 }}>
              <div style={summaryGrid}>
                <Summary label="Status" value={label(selected.status)} />
                <Summary label="Current stage" value={label(selected.current_stage)} />
                <Summary label="Angle" value={label(selected.angle_type)} />
                <Summary label="Platforms" value={selected.requested_platforms.map(label).join(", ")} />
              </div>

              <div style={callout}>
                <strong>Evidence thesis</strong>
                <p style={{ marginBottom: 6 }}>{evidence?.thesis ?? "No evidence pack loaded."}</p>
                <small style={muted}>
                  {supportedClaims.length} supported claim(s) available for factual grounding.
                </small>
              </div>

              <button disabled={busy} onClick={runSelected} style={primaryButton}>
                {selected.artifacts.length > 0 ? "Run new stage revisions" : "Generate all stages"}
              </button>

              <div style={{ display: "grid", gap: 12 }}>
                {stages.length === 0 && <p style={muted}>Run the workflow to create stage artifacts.</p>}
                {stages.map((artifact) => (
                  <article key={artifact.id} style={artifactCard}>
                    <div style={{ display: "flex", justifyContent: "space-between", gap: 12 }}>
                      <div>
                        <strong>{label(artifact.stage)}</strong>
                        <div style={muted}>
                          Revision {artifact.revision} · {label(artifact.source)}
                          {artifact.prompt_version ? ` · ${artifact.prompt_version}` : ""}
                        </div>
                      </div>
                      {EDITABLE_STAGES.has(artifact.stage) && (
                        <button disabled={busy} onClick={() => beginEdit(artifact)} style={smallButton}>
                          Edit
                        </button>
                      )}
                    </div>
                    <pre style={contentPreview}>{artifact.content}</pre>
                    {artifact.claim_references.length > 0 && (
                      <p style={muted}>
                        {artifact.claim_references.length} factual statement(s) mapped to evidence.
                      </p>
                    )}
                    {Object.keys(artifact.structured_data).length > 0 &&
                      ["fact_check", "quality_evaluation"].includes(artifact.stage) && (
                        <details>
                          <summary>Inspect report</summary>
                          <pre style={reportPreview}>
                            {JSON.stringify(artifact.structured_data, null, 2)}
                          </pre>
                        </details>
                      )}
                  </article>
                ))}
              </div>

              {editForm.stage && (
                <form onSubmit={saveRevision} style={editorCard}>
                  <h3 style={{ marginTop: 0 }}>Append {label(editForm.stage)} revision</h3>
                  <Field label="Content">
                    <textarea
                      required
                      rows={10}
                      value={editForm.content}
                      onChange={(event) => setEditForm({ ...editForm, content: event.target.value })}
                    />
                  </Field>
                  <Field label="Grounded claim">
                    <select
                      value={editForm.claim_id}
                      onChange={(event) => setEditForm({ ...editForm, claim_id: event.target.value })}
                    >
                      <option value="">No factual claim reference</option>
                      {supportedClaims.map((claim) => (
                        <option key={claim.id} value={claim.id}>
                          {claim.statement}
                        </option>
                      ))}
                    </select>
                  </Field>
                  <Field label="Revision note">
                    <input
                      value={editForm.note}
                      onChange={(event) => setEditForm({ ...editForm, note: event.target.value })}
                    />
                  </Field>
                  <div style={{ display: "flex", gap: 8 }}>
                    <button disabled={busy} type="submit" style={primaryButton}>
                      Save revision
                    </button>
                    <button
                      type="button"
                      onClick={() => setEditForm({ stage: "", content: "", claim_id: "", note: "" })}
                      style={smallButton}
                    >
                      Cancel
                    </button>
                  </div>
                </form>
              )}

              {selected.approvals.length > 0 && (
                <div style={{ display: "grid", gap: 10 }}>
                  <h3 style={{ marginBottom: 0 }}>Local approval</h3>
                  <p style={{ ...muted, marginTop: 0 }}>
                    This records review state only. There is no publishing integration.
                  </p>
                  {selected.approvals.map((approval) => (
                    <div key={approval.id}>
                      <div style={approvalRow}>
                        <div>
                          <strong>{label(approval.platform)}</strong>
                          <div style={{ color: statusColor(approval.decision) }}>
                            {label(approval.decision)} · Level {approval.required_level}
                          </div>
                        </div>
                        <div style={{ display: "flex", gap: 8 }}>
                          <button
                            disabled={busy}
                            onClick={() => void previewDuplicate(approval.platform)}
                            style={smallButton}
                          >
                            Check content memory
                          </button>
                          <button
                            disabled={busy}
                            onClick={() => decide(approval.platform, "approved")}
                            style={approveButton}
                          >
                            Approve
                          </button>
                          <button
                            disabled={busy}
                            onClick={() => decide(approval.platform, "rejected")}
                            style={rejectButton}
                          >
                            Reject
                          </button>
                        </div>
                      </div>
                      <DuplicatePanel
                        preview={duplicatePreviews[approval.platform] ?? null}
                        overrideReason={overrideReasons[approval.platform] ?? ""}
                        onOverrideReasonChange={(value) =>
                          setOverrideReasons((current) => ({ ...current, [approval.platform]: value }))
                        }
                      />
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </Section>
      </div>
    </div>
  );
}

function Section({ title, description, children }: { title: string; description: string; children: ReactNode }) {
  return (
    <section style={sectionStyle}>
      <h2 style={{ margin: 0 }}>{title}</h2>
      <p style={{ ...muted, marginTop: 6 }}>{description}</p>
      {children}
    </section>
  );
}

function Field({ label: fieldLabel, children }: { label: string; children: ReactNode }) {
  return (
    <label style={{ display: "grid", gap: 6 }}>
      <span style={{ fontWeight: 600 }}>{fieldLabel}</span>
      {children}
    </label>
  );
}

function Metric({ label: metricLabel, value }: { label: string; value: number }) {
  return (
    <div style={metricCard}>
      <strong style={{ fontSize: 24 }}>{value}</strong>
      <span style={muted}>{metricLabel}</span>
    </div>
  );
}

function Summary({ label: summaryLabel, value }: { label: string; value: string }) {
  return (
    <div>
      <div style={muted}>{summaryLabel}</div>
      <strong>{value}</strong>
    </div>
  );
}

function statusColor(status: string) {
  if (status === "approved" || status === "ready_for_approval") return "#166534";
  if (status === "rejected" || status === "fact_check_failed") return "#b91c1c";
  return "#92400e";
}

const muted = { color: "#6b7280", fontSize: 14 };
const metricGrid = {
  display: "grid",
  gridTemplateColumns: "repeat(auto-fit, minmax(150px, 1fr))",
  gap: 12,
  marginBottom: 20,
};
const metricCard = {
  display: "grid",
  gap: 4,
  padding: 16,
  border: "1px solid #e5e7eb",
  borderRadius: 12,
  background: "#f9fafb",
};
const sectionStyle = {
  border: "1px solid #e5e7eb",
  borderRadius: 14,
  padding: 18,
  marginBottom: 20,
  background: "white",
};
const formGrid = {
  display: "grid",
  gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))",
  alignItems: "end",
  gap: 14,
};
const primaryButton = {
  border: 0,
  borderRadius: 8,
  background: "#1d4ed8",
  color: "white",
  padding: "10px 14px",
  fontWeight: 700,
  cursor: "pointer",
};
const smallButton = {
  border: "1px solid #d1d5db",
  borderRadius: 8,
  background: "white",
  padding: "7px 11px",
  cursor: "pointer",
};
const queueButton = {
  display: "grid",
  gap: 4,
  textAlign: "left" as const,
  border: "1px solid #d1d5db",
  borderRadius: 10,
  padding: 12,
  cursor: "pointer",
};
const summaryGrid = {
  display: "grid",
  gridTemplateColumns: "repeat(auto-fit, minmax(130px, 1fr))",
  gap: 12,
};
const callout = { padding: 14, borderRadius: 10, background: "#f0fdf4", border: "1px solid #bbf7d0" };
const artifactCard = { padding: 14, borderRadius: 10, border: "1px solid #d1d5db" };
const contentPreview = {
  whiteSpace: "pre-wrap" as const,
  fontFamily: "inherit",
  lineHeight: 1.5,
  padding: 12,
  borderRadius: 8,
  background: "#f9fafb",
  maxHeight: 320,
  overflow: "auto",
};
const reportPreview = {
  whiteSpace: "pre-wrap" as const,
  fontSize: 12,
  background: "#111827",
  color: "#f9fafb",
  padding: 12,
  borderRadius: 8,
  overflow: "auto",
};
const editorCard = { padding: 16, borderRadius: 10, border: "2px solid #93c5fd", background: "#eff6ff" };
const approvalRow = {
  display: "flex",
  justifyContent: "space-between",
  alignItems: "center",
  gap: 12,
  padding: 12,
  border: "1px solid #d1d5db",
  borderRadius: 10,
};
const approveButton = { ...smallButton, borderColor: "#86efac", color: "#166534" };
const rejectButton = { ...smallButton, borderColor: "#fca5a5", color: "#b91c1c" };

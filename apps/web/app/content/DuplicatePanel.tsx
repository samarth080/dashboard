"use client";

export interface DuplicateNeighbour {
  post_record_id: string;
  platform: string;
  lexical: number;
  semantic: number | null;
  score: number;
}

export interface DuplicatePreview {
  verdict: "clear" | "warn" | "block";
  config_version: string;
  top_similarity: number;
  neighbours: DuplicateNeighbour[];
}

const VERDICT_COLOR: Record<DuplicatePreview["verdict"], string> = {
  clear: "#166534",
  warn: "#b45309",
  block: "#b91c1c",
};

const VERDICT_TEXT: Record<DuplicatePreview["verdict"], string> = {
  clear: "No similar post found in history.",
  warn: "Similar to an existing post. Approval is still allowed.",
  block: "Too similar to an existing post. Approval requires an override reason.",
};

function formatScore(value: number | null) {
  return value === null ? "—" : value.toFixed(2);
}

export function DuplicatePanel({
  preview,
  overrideReason,
  onOverrideReasonChange,
}: {
  preview: DuplicatePreview | null;
  overrideReason: string;
  onOverrideReasonChange: (value: string) => void;
}) {
  if (!preview) return null;

  return (
    <section
      style={{
        border: "1px solid #e5e7eb",
        borderRadius: 8,
        padding: 16,
        marginTop: 16,
      }}
    >
      <h3 style={{ marginTop: 0, marginBottom: 4 }}>Content memory check</h3>
      <p style={{ color: VERDICT_COLOR[preview.verdict], marginTop: 0 }}>
        <strong>{preview.verdict.toUpperCase()}</strong> · similarity{" "}
        {formatScore(preview.top_similarity)} · policy {preview.config_version}
      </p>
      <p style={{ color: "#4b5563", marginTop: 0 }}>{VERDICT_TEXT[preview.verdict]}</p>

      {preview.neighbours.length > 0 && (
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 14 }}>
          <thead>
            <tr style={{ textAlign: "left", color: "#6b7280" }}>
              <th style={{ padding: "4px 0" }}>Existing post</th>
              <th>Platform</th>
              <th>Lexical</th>
              <th>Semantic</th>
              <th>Score</th>
            </tr>
          </thead>
          <tbody>
            {preview.neighbours.slice(0, 5).map((item) => (
              <tr key={item.post_record_id} style={{ borderTop: "1px solid #f3f4f6" }}>
                <td style={{ padding: "4px 0" }}>{item.post_record_id.slice(0, 8)}</td>
                <td>{item.platform}</td>
                <td>{formatScore(item.lexical)}</td>
                <td>{formatScore(item.semantic)}</td>
                <td>
                  <strong>{formatScore(item.score)}</strong>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {preview.verdict === "block" && (
        <label style={{ display: "block", marginTop: 12 }}>
          <span style={{ display: "block", marginBottom: 4 }}>
            Override reason (required to approve)
          </span>
          <input
            value={overrideReason}
            onChange={(event) => onOverrideReasonChange(event.target.value)}
            placeholder="Why is this near-duplicate intentional?"
            style={{ width: "100%", padding: 8, border: "1px solid #d1d5db", borderRadius: 6 }}
          />
        </label>
      )}
    </section>
  );
}

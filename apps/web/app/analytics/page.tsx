"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

interface Snapshot {
  id: string;
  captured_at: string;
  source: string;
  is_mock: boolean;
  impressions: number | null;
  reactions: number | null;
  comments: number | null;
  reposts: number | null;
  clicks: number | null;
  follows: number | null;
}

interface PostRecord {
  id: string;
  platform: string;
  origin: string;
  status: string;
  content: string;
  external_url: string | null;
  posted_at: string | null;
  snapshots: Snapshot[];
  created_at: string;
}

export default function AnalyticsPage() {
  const [posts, setPosts] = useState<PostRecord[]>([]);
  const [error, setError] = useState("");
  const [form, setForm] = useState({ platform: "linkedin", content: "", external_url: "" });

  const load = useCallback(async () => {
    try {
      const response = await fetch(`${API_URL}/api/memory/posts`);
      if (!response.ok) throw new Error(await response.text());
      setPosts((await response.json()) as PostRecord[]);
      setError("");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Failed to load posts.");
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  async function addPost(event: FormEvent) {
    event.preventDefault();
    try {
      const response = await fetch(`${API_URL}/api/memory/posts`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          platform: form.platform,
          content: form.content,
          external_url: form.external_url || null,
        }),
      });
      if (!response.ok) throw new Error(await response.text());
      setForm({ platform: "linkedin", content: "", external_url: "" });
      await load();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Failed to add post.");
    }
  }

  async function capture(postId: string) {
    try {
      const response = await fetch(`${API_URL}/api/memory/posts/${postId}/metrics`, {
        method: "POST",
      });
      if (!response.ok) throw new Error(await response.text());
      await load();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Failed to capture metrics.");
    }
  }

  return (
    <div style={{ maxWidth: 1180, margin: "0 auto", fontFamily: "system-ui, sans-serif" }}>
      <header style={{ marginBottom: 24 }}>
        <p style={{ color: "#6b7280", marginBottom: 4 }}>M4 · Content Memory</p>
        <h1 style={{ margin: 0 }}>Post history</h1>
        <p style={{ color: "#4b5563" }}>
          Posts you published elsewhere, or drafts approved here and not yet published. Metrics
          come from a deterministic mock provider and are never real platform data.
        </p>
      </header>

      {error && <p style={{ color: "#b91c1c" }}>{error}</p>}

      <form onSubmit={addPost} style={{ marginBottom: 24, display: "grid", gap: 8 }}>
        <h2 style={{ marginBottom: 0 }}>Record a post published elsewhere</h2>
        <select
          value={form.platform}
          onChange={(event) => setForm({ ...form, platform: event.target.value })}
          style={{ padding: 8, maxWidth: 200 }}
        >
          <option value="linkedin">LinkedIn</option>
          <option value="x">X</option>
        </select>
        <textarea
          value={form.content}
          onChange={(event) => setForm({ ...form, content: event.target.value })}
          placeholder="Post text"
          required
          rows={4}
          style={{ padding: 8 }}
        />
        <input
          value={form.external_url}
          onChange={(event) => setForm({ ...form, external_url: event.target.value })}
          placeholder="https://… (optional)"
          style={{ padding: 8 }}
        />
        <button type="submit" style={{ padding: 8, maxWidth: 160 }}>
          Add to history
        </button>
      </form>

      {posts.length === 0 && <p style={{ color: "#6b7280" }}>No posts recorded yet.</p>}

      {posts.map((post) => {
        const latest = post.snapshots[post.snapshots.length - 1];
        return (
          <article
            key={post.id}
            style={{
              border: "1px solid #e5e7eb",
              borderRadius: 8,
              padding: 16,
              marginBottom: 12,
            }}
          >
            <div style={{ display: "flex", justifyContent: "space-between", gap: 16 }}>
              <div>
                <strong>{post.platform === "linkedin" ? "LinkedIn" : "X"}</strong>
                <span style={{ color: "#6b7280" }}>
                  {" "}
                  · {post.origin} · {post.status.replace(/_/g, " ")}
                </span>
              </div>
              <button type="button" onClick={() => void capture(post.id)}>
                Capture mock metrics
              </button>
            </div>
            <p style={{ whiteSpace: "pre-wrap", color: "#111827" }}>{post.content}</p>
            {latest ? (
              <p style={{ color: "#4b5563", fontSize: 14 }}>
                {latest.impressions ?? "—"} impressions · {latest.reactions ?? "—"} reactions ·{" "}
                {latest.comments ?? "—"} comments · {latest.reposts ?? "—"} reposts ·{" "}
                {post.snapshots.length} snapshot(s)
                {latest.is_mock && " · mock data"}
              </p>
            ) : (
              <p style={{ color: "#6b7280", fontSize: 14 }}>No metrics captured yet.</p>
            )}
          </article>
        );
      })}
    </div>
  );
}

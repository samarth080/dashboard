"use client";

import { FormEvent, useEffect, useState } from "react";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

interface Profile {
  id: string;
  display_name: string;
  headline: string | null;
  bio: string | null;
  location: string | null;
}

interface Interest {
  id: string;
  parent_id: string | null;
  name: string;
  description: string | null;
  weight: string;
  enabled: boolean;
}

interface WritingSample {
  id: string;
  title: string | null;
  content: string;
  source_label: string;
}

interface VoiceProfile {
  summary: string;
  tone_descriptors: string[];
  signature_traits: string[];
  sample_count: number;
  confidence: string;
  analysis_prompt_version: string;
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

function commaList(value: string): string[] {
  return value
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}

export default function SettingsPage() {
  const [profile, setProfile] = useState({
    display_name: "",
    headline: "",
    bio: "",
    location: "",
  });
  const [career, setCareer] = useState({
    current_title: "",
    current_company: "",
    years_experience: "",
    target_roles: "",
    target_industries: "",
    skills: "",
    goals: "",
  });
  const [settings, setSettings] = useState({
    timezone: "UTC",
    locale: "en",
    daily_llm_budget_usd: "5.00",
    public_action_approval_level: "1",
    memory_enabled: true,
  });
  const [interests, setInterests] = useState<Interest[]>([]);
  const [newInterest, setNewInterest] = useState({
    name: "",
    weight: "0.500",
    parent_id: "",
  });
  const [samples, setSamples] = useState<WritingSample[]>([]);
  const [sampleForm, setSampleForm] = useState({ title: "", content: "", confirmed: false });
  const [voice, setVoice] = useState<VoiceProfile | null>(null);
  const [hasProfile, setHasProfile] = useState(false);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("Loading Personal Brain…");
  const [error, setError] = useState<string | null>(null);

  async function load() {
    setError(null);
    try {
      const loadedProfile = await requestOptional<Profile>("/api/profile");
      if (!loadedProfile) {
        setHasProfile(false);
        setNotice("Create your profile to unlock career, interests, and voice settings.");
        return;
      }
      setHasProfile(true);
      setProfile({
        display_name: loadedProfile.display_name,
        headline: loadedProfile.headline ?? "",
        bio: loadedProfile.bio ?? "",
        location: loadedProfile.location ?? "",
      });

      const [loadedCareer, loadedSettings, loadedInterests, loadedSamples, loadedVoice] =
        await Promise.all([
          requestOptional<{
            current_title: string | null;
            current_company: string | null;
            years_experience: string | null;
            target_roles: string[];
            target_industries: string[];
            skills: string[];
            goals: string[];
          }>("/api/profile/career"),
          requestOptional<{
            timezone: string;
            locale: string;
            daily_llm_budget_usd: string;
            public_action_approval_level: number;
            memory_enabled: boolean;
          }>("/api/settings"),
          request<Interest[]>("/api/interests"),
          request<WritingSample[]>("/api/voice/samples"),
          requestOptional<VoiceProfile>("/api/voice"),
        ]);

      if (loadedCareer) {
        setCareer({
          current_title: loadedCareer.current_title ?? "",
          current_company: loadedCareer.current_company ?? "",
          years_experience: loadedCareer.years_experience ?? "",
          target_roles: loadedCareer.target_roles.join(", "),
          target_industries: loadedCareer.target_industries.join(", "),
          skills: loadedCareer.skills.join(", "),
          goals: loadedCareer.goals.join(", "),
        });
      }
      if (loadedSettings) {
        setSettings({
          timezone: loadedSettings.timezone,
          locale: loadedSettings.locale,
          daily_llm_budget_usd: loadedSettings.daily_llm_budget_usd,
          public_action_approval_level: String(loadedSettings.public_action_approval_level),
          memory_enabled: loadedSettings.memory_enabled,
        });
      }
      setInterests(loadedInterests);
      setSamples(loadedSamples);
      setVoice(loadedVoice);
      setNotice("Personal Brain loaded.");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
      setNotice("");
    }
  }

  useEffect(() => {
    void load();
  }, []);

  async function runAction(action: () => Promise<void>, success: string) {
    setBusy(true);
    setError(null);
    try {
      await action();
      setNotice(success);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setBusy(false);
    }
  }

  function saveProfile(event: FormEvent) {
    event.preventDefault();
    void runAction(async () => {
      await request<Profile>("/api/profile", {
        method: "PUT",
        body: JSON.stringify({
          display_name: profile.display_name,
          headline: profile.headline || null,
          bio: profile.bio || null,
          location: profile.location || null,
        }),
      });
      setHasProfile(true);
    }, "Profile saved.");
  }

  function saveCareer(event: FormEvent) {
    event.preventDefault();
    void runAction(async () => {
      await request("/api/profile/career", {
        method: "PUT",
        body: JSON.stringify({
          current_title: career.current_title || null,
          current_company: career.current_company || null,
          years_experience: career.years_experience || null,
          target_roles: commaList(career.target_roles),
          target_industries: commaList(career.target_industries),
          skills: commaList(career.skills),
          goals: commaList(career.goals),
        }),
      });
    }, "Career profile saved.");
  }

  function saveSettings(event: FormEvent) {
    event.preventDefault();
    void runAction(async () => {
      await request("/api/settings", {
        method: "PUT",
        body: JSON.stringify({
          ...settings,
          public_action_approval_level: Number(settings.public_action_approval_level),
        }),
      });
    }, "Preferences saved.");
  }

  function addInterest(event: FormEvent) {
    event.preventDefault();
    void runAction(async () => {
      const created = await request<Interest>("/api/interests", {
        method: "POST",
        body: JSON.stringify({
          name: newInterest.name,
          weight: newInterest.weight,
          parent_id: newInterest.parent_id || null,
        }),
      });
      setInterests((current) => [...current, created].sort((a, b) => a.name.localeCompare(b.name)));
      setNewInterest({ name: "", weight: "0.500", parent_id: "" });
    }, "Interest added.");
  }

  function toggleInterest(interest: Interest) {
    void runAction(async () => {
      const updated = await request<Interest>(`/api/interests/${interest.id}`, {
        method: "PATCH",
        body: JSON.stringify({ enabled: !interest.enabled }),
      });
      setInterests((current) => current.map((item) => (item.id === updated.id ? updated : item)));
    }, `${interest.name} ${interest.enabled ? "disabled" : "enabled"}.`);
  }

  function removeInterest(interest: Interest) {
    void runAction(async () => {
      const response = await fetch(`${API_URL}/api/interests/${interest.id}`, { method: "DELETE" });
      if (!response.ok) throw new Error("Could not delete interest");
      setInterests((current) =>
        current
          .filter((item) => item.id !== interest.id)
          .map((item) => (item.parent_id === interest.id ? { ...item, parent_id: null } : item)),
      );
    }, `${interest.name} removed.`);
  }

  function addSample(event: FormEvent) {
    event.preventDefault();
    void runAction(async () => {
      const created = await request<WritingSample>("/api/voice/samples", {
        method: "POST",
        body: JSON.stringify({
          title: sampleForm.title || null,
          content: sampleForm.content,
          confirmed_user_provided: sampleForm.confirmed,
        }),
      });
      setSamples((current) => [...current, created]);
      setSampleForm({ title: "", content: "", confirmed: false });
    }, "Writing sample saved.");
  }

  function analyzeVoice() {
    void runAction(async () => {
      const analyzed = await request<VoiceProfile>("/api/voice/analyze", { method: "POST" });
      setVoice(analyzed);
    }, "Voice profile analyzed with the versioned v1 prompt.");
  }

  return (
    <div style={{ maxWidth: 980, margin: "0 auto", fontFamily: "system-ui, sans-serif" }}>
      <header style={{ marginBottom: 24 }}>
        <p style={{ color: "#6b7280", marginBottom: 4 }}>M1 · Personal Brain</p>
        <h1 style={{ margin: 0 }}>Profile & settings</h1>
        <p style={{ color: "#4b5563" }}>
          This is the editable source of truth used by later research, content, job, and network
          workflows.
        </p>
        {notice && <p style={{ color: "#166534" }}>{notice}</p>}
        {error && <p style={{ color: "#b91c1c" }}>{error}</p>}
      </header>

      <Section title="Identity" description="Basic details you want the engine to use.">
        <form onSubmit={saveProfile} style={formGrid}>
          <Field label="Display name">
            <input
              required
              value={profile.display_name}
              onChange={(event) => setProfile({ ...profile, display_name: event.target.value })}
            />
          </Field>
          <Field label="Headline">
            <input
              value={profile.headline}
              onChange={(event) => setProfile({ ...profile, headline: event.target.value })}
            />
          </Field>
          <Field label="Location">
            <input
              value={profile.location}
              onChange={(event) => setProfile({ ...profile, location: event.target.value })}
            />
          </Field>
          <Field label="Bio" wide>
            <textarea
              rows={4}
              value={profile.bio}
              onChange={(event) => setProfile({ ...profile, bio: event.target.value })}
            />
          </Field>
          <button disabled={busy} type="submit">
            Save profile
          </button>
        </form>
      </Section>

      <Section title="Career direction" description="Comma-separate lists; nothing is niche-specific.">
        <form onSubmit={saveCareer} style={formGrid}>
          <Field label="Current title">
            <input
              disabled={!hasProfile}
              value={career.current_title}
              onChange={(event) => setCareer({ ...career, current_title: event.target.value })}
            />
          </Field>
          <Field label="Current company">
            <input
              disabled={!hasProfile}
              value={career.current_company}
              onChange={(event) => setCareer({ ...career, current_company: event.target.value })}
            />
          </Field>
          <Field label="Years of experience">
            <input
              disabled={!hasProfile}
              min="0"
              max="80"
              step="0.5"
              type="number"
              value={career.years_experience}
              onChange={(event) => setCareer({ ...career, years_experience: event.target.value })}
            />
          </Field>
          {(["target_roles", "target_industries", "skills", "goals"] as const).map((key) => (
            <Field key={key} label={key.replaceAll("_", " ")}>
              <input
                disabled={!hasProfile}
                value={career[key]}
                onChange={(event) => setCareer({ ...career, [key]: event.target.value })}
              />
            </Field>
          ))}
          <button disabled={busy || !hasProfile} type="submit">
            Save career profile
          </button>
        </form>
      </Section>

      <Section title="Preferences" description="User preferences—not server environment variables.">
        <form onSubmit={saveSettings} style={formGrid}>
          <Field label="IANA timezone">
            <input
              disabled={!hasProfile}
              value={settings.timezone}
              onChange={(event) => setSettings({ ...settings, timezone: event.target.value })}
            />
          </Field>
          <Field label="Locale">
            <input
              disabled={!hasProfile}
              value={settings.locale}
              onChange={(event) => setSettings({ ...settings, locale: event.target.value })}
            />
          </Field>
          <Field label="Daily LLM budget (USD)">
            <input
              disabled={!hasProfile}
              min="0"
              step="0.01"
              type="number"
              value={settings.daily_llm_budget_usd}
              onChange={(event) =>
                setSettings({ ...settings, daily_llm_budget_usd: event.target.value })
              }
            />
          </Field>
          <Field label="Public action approval level">
            <select
              disabled={!hasProfile}
              value={settings.public_action_approval_level}
              onChange={(event) =>
                setSettings({ ...settings, public_action_approval_level: event.target.value })
              }
            >
              <option value="1">Level 1 · Always ask</option>
              <option value="2">Level 2</option>
              <option value="3">Level 3</option>
            </select>
          </Field>
          <label style={{ display: "flex", gap: 8, alignItems: "center" }}>
            <input
              checked={settings.memory_enabled}
              disabled={!hasProfile}
              type="checkbox"
              onChange={(event) => setSettings({ ...settings, memory_enabled: event.target.checked })}
            />
            Enable persisted memory
          </label>
          <button disabled={busy || !hasProfile} type="submit">
            Save preferences
          </button>
        </form>
      </Section>

      <Section title="Interest graph" description="Weighted, hierarchical, and fully configurable.">
        <form onSubmit={addInterest} style={formGrid}>
          <Field label="Interest">
            <input
              disabled={!hasProfile}
              required
              value={newInterest.name}
              onChange={(event) => setNewInterest({ ...newInterest, name: event.target.value })}
            />
          </Field>
          <Field label="Weight (0–1)">
            <input
              disabled={!hasProfile}
              max="1"
              min="0"
              step="0.05"
              type="number"
              value={newInterest.weight}
              onChange={(event) => setNewInterest({ ...newInterest, weight: event.target.value })}
            />
          </Field>
          <Field label="Parent">
            <select
              disabled={!hasProfile}
              value={newInterest.parent_id}
              onChange={(event) => setNewInterest({ ...newInterest, parent_id: event.target.value })}
            >
              <option value="">None</option>
              {interests.map((interest) => (
                <option key={interest.id} value={interest.id}>
                  {interest.name}
                </option>
              ))}
            </select>
          </Field>
          <button disabled={busy || !hasProfile} type="submit">
            Add interest
          </button>
        </form>
        <div style={{ display: "grid", gap: 8, marginTop: 16 }}>
          {interests.map((interest) => (
            <div key={interest.id} style={rowStyle}>
              <div>
                <strong>{interest.name}</strong> · {interest.weight}
                {interest.parent_id && (
                  <span style={{ color: "#6b7280" }}>
                    {" "}under {interests.find((item) => item.id === interest.parent_id)?.name}
                  </span>
                )}
              </div>
              <div style={{ display: "flex", gap: 8 }}>
                <button disabled={busy} type="button" onClick={() => toggleInterest(interest)}>
                  {interest.enabled ? "Disable" : "Enable"}
                </button>
                <button disabled={busy} type="button" onClick={() => removeInterest(interest)}>
                  Remove
                </button>
              </div>
            </div>
          ))}
          {hasProfile && interests.length === 0 && <p>No interests yet.</p>}
        </div>
      </Section>

      <Section
        title="Voice profile"
        description="Analysis uses only writing you affirmatively provide here."
      >
        <form onSubmit={addSample} style={formGrid}>
          <Field label="Sample title">
            <input
              disabled={!hasProfile}
              value={sampleForm.title}
              onChange={(event) => setSampleForm({ ...sampleForm, title: event.target.value })}
            />
          </Field>
          <Field label="Writing sample (minimum 50 characters)" wide>
            <textarea
              disabled={!hasProfile}
              minLength={50}
              required
              rows={7}
              value={sampleForm.content}
              onChange={(event) => setSampleForm({ ...sampleForm, content: event.target.value })}
            />
          </Field>
          <label style={{ display: "flex", gap: 8, alignItems: "center", gridColumn: "1 / -1" }}>
            <input
              checked={sampleForm.confirmed}
              disabled={!hasProfile}
              required
              type="checkbox"
              onChange={(event) => setSampleForm({ ...sampleForm, confirmed: event.target.checked })}
            />
            I confirm this is writing I explicitly provided for voice analysis.
          </label>
          <button disabled={busy || !hasProfile} type="submit">
            Add writing sample
          </button>
        </form>
        <p>{samples.length} confirmed sample(s) stored.</p>
        <button disabled={busy || samples.length === 0} type="button" onClick={analyzeVoice}>
          Analyze voice
        </button>
        {voice && (
          <div style={{ ...rowStyle, display: "block", marginTop: 16 }}>
            <strong>{voice.summary}</strong>
            <p>
              Tone: {voice.tone_descriptors.join(", ") || "insufficient evidence"} · confidence {" "}
              {voice.confidence} · {voice.sample_count} sample(s)
            </p>
            <p>Signature traits: {voice.signature_traits.join(", ") || "insufficient evidence"}</p>
            <small>Prompt: {voice.analysis_prompt_version}</small>
          </div>
        )}
      </Section>
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
    <section style={{ borderTop: "1px solid #e5e7eb", padding: "24px 0" }}>
      <h2 style={{ marginBottom: 4 }}>{title}</h2>
      <p style={{ color: "#6b7280", marginTop: 0 }}>{description}</p>
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
      <span style={{ fontSize: 14, fontWeight: 600 }}>{label}</span>
      {children}
    </label>
  );
}

const formGrid = {
  display: "grid",
  gridTemplateColumns: "repeat(auto-fit, minmax(240px, 1fr))",
  gap: 16,
  alignItems: "end",
};

const rowStyle = {
  border: "1px solid #e5e7eb",
  borderRadius: 8,
  padding: 12,
  display: "flex",
  justifyContent: "space-between",
  gap: 12,
  alignItems: "center",
};

"use client";

import { useEffect, useState } from "react";

interface HealthResponse {
  status: string;
  run_id: string;
}

export default function TodayPage() {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const apiUrl = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
    fetch(`${apiUrl}/api/health`)
      .then((res) => res.json())
      .then(setHealth)
      .catch((err) => setError(String(err)));
  }, []);

  return (
    <div>
      <h1>Today</h1>
      {error && <p>API error: {error}</p>}
      {health && (
        <p>
          API status: {health.status} (run_id: {health.run_id})
        </p>
      )}
      {!health && !error && <p>Checking API health...</p>}
    </div>
  );
}

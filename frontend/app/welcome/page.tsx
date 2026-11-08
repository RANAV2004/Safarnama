"use client";
// welcome page
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import InterestIcon from "@/components/InterestIcon";
import { AuthError, getProfile, saveProfile, type Interest } from "@/lib/api";
import { clearSession, getSession } from "@/lib/auth";

export default function Welcome() {
  const router = useRouter();
  const [options, setOptions] = useState<Interest[]>([]);
  const [picked, setPicked] = useState<string[]>([]);
  const [editing, setEditing] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  useEffect(() => {
    const s = getSession();
    if (!s) {
      router.replace("/login");
      return;
    }
    getProfile()
      .then((p) => {
        setOptions(p.options);
        setPicked(p.interests);
        setEditing(p.onboarded);
      })
      .catch((e) => {
        if (e instanceof AuthError) {
          clearSession();
          router.replace("/login?expired=1");
        } else setError((e as Error).message);
      });
  }, [router]);
  function toggle(id: string) {
    setPicked((p) => (p.includes(id) ? p.filter((x) => x !== id) : [...p, id]));
  }
  async function save(list: string[]) {
    setBusy(true);
    setError("");
    try {
      await saveProfile(list);
      router.replace("/dashboard");
    } catch (e) {
      setError((e as Error).message);
      setBusy(false);
    }
  }
  return (
    <main className="welcome">
      <div className="welcome-card">
        <p className="brand">
          Safarnama <span lang="hi">सफ़रनामा</span>
        </p>
        <div className="stack">
          <h1>{editing ? "Your travel interests" : "What do you love when you travel?"}</h1>
          <p className="muted">
            Pick as many as you like. Every itinerary will put these first. You can change them any time.
          </p>
        </div>
        {options.length === 0 && !error && <p className="muted">Loading</p>}
        <div className="interests" role="group" aria-label="Travel interests">
          {options.map((o) => (
            <button
              key={o.id}
              type="button"
              className="interest"
              aria-pressed={picked.includes(o.id)}
              onClick={() => toggle(o.id)}
            >
              <InterestIcon id={o.id} />
              <span className="interest-label">{o.label}</span>
              <span className="interest-hint">{o.hint}</span>
            </button>
          ))}
        </div>
        {error && (
          <p className="error" role="alert">
            {error}
          </p>
        )}
        <div className="welcome-actions">
          <button
            type="button"
            className="btn-primary"
            disabled={busy || picked.length === 0}
            onClick={() => save(picked)}
          >
            {busy
              ? "Saving"
              : picked.length
                ? `Save ${picked.length} interest${picked.length > 1 ? "s" : ""} and continue`
                : "Pick at least one"}
          </button>
          {!editing && (
            <button type="button" className="link" disabled={busy} onClick={() => save([])}>
              Skip for now
            </button>
          )}
          {editing && (
            <button type="button" className="link" disabled={busy} onClick={() => router.replace("/dashboard")}>
              Cancel
            </button>
          )}
        </div>
      </div>
    </main>
  );
}

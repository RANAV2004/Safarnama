"use client";
// settings page
import Link from "next/link";
import { useEffect, useState } from "react";
import TopBar from "@/components/TopBar";
import { AuthError, changePassword, deleteTrip, myTrips, type TripSummary } from "@/lib/api";
import { saveSession } from "@/lib/auth";
import { rupees, shortDate } from "@/lib/format";
import { useAccount } from "@/lib/useAccount";
const FAQ = [
  [
    "How does Safarnama plan my trip?",
    "Separate agents look for travel, a hotel and places to visit at the same time. A coordinator moves money between them if the plan goes over budget, and a critic checks the final plan for things like closed days or a hotel desk that shuts before you arrive.",
  ],
  [
    "Are the prices real?",
    "Right now the prices and timings come from sample data, so treat them as estimates and check them before you book anything. Safarnama does not book or take payment.",
  ],
  [
    "How do I change my plan?",
    "Use Change and Remove on the itinerary, or type what you want in the chat under it, like remove the flea market and add another beach. Regenerate keeps your choices fixed and replans the rest.",
  ],
  [
    "What does the chat learn?",
    "When you press Yes or Not right under a reply, Safarnama saves your wording as a training example and retrains its own model. Your likes and dislikes are saved only to your account. Use Forget under the chat to clear them.",
  ],
  [
    "Where are my itineraries?",
    "Every itinerary you generate is saved automatically under My itineraries on this page. Open one to keep editing it, or delete it.",
  ],
  [
    "I forgot my password",
    "On the sign in page, choose Forgot password. We email you a 6 digit code, then you choose a new password. If you are signed in, change it on this page.",
  ],
  [
    "My account was suspended",
    "An admin can suspend accounts that break the rules. Contact the Safarnama team if you think this is a mistake.",
  ],
];

export default function Settings() {
  const { user, expired } = useAccount();
  const [trips, setTrips] = useState<TripSummary[] | null>(null);
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    if (!user) return;
    myTrips()
      .then(setTrips)
      .catch((e) => e instanceof AuthError && expired());
  }, [user?.id]);
  async function remove(t: TripSummary) {
    if (!window.confirm(`Delete ${t.origin} to ${t.destination}? This cannot be undone.`)) return;
    await deleteTrip(t.id).catch(() => {});
    setTrips((old) => (old ?? []).filter((x) => x.id !== t.id));
  }
  async function change(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setMsg(null);
    try {
      const s = await changePassword(current, next);
      saveSession(s);
      setCurrent("");
      setNext("");
      setMsg({ ok: true, text: "Password changed. Other devices have been signed out." });
    } catch (err) {
      if (err instanceof AuthError) return expired();
      setMsg({ ok: false, text: (err as Error).message });
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="page">
      <TopBar user={user} />
      <main className="settings">
        <nav className="side" aria-label="Settings sections">
          <a href="#profile">Profile</a>
          <a href="#trips">My itineraries</a>
          <a href="#password">Password</a>
          <a href="#help">Help center</a>
        </nav>
        <div className="settings-body">
          <section id="profile" className="card">
            <h2>Profile</h2>
            {user && (
              <dl className="facts">
                <div>
                  <dt>Name</dt>
                  <dd>{user.name}</dd>
                </div>
                <div>
                  <dt>Email</dt>
                  <dd>{user.email}</dd>
                </div>
                <div>
                  <dt>Date of birth</dt>
                  <dd>
                    {new Date(`${user.birth_date}T00:00:00`).toLocaleDateString("en-IN", {
                      day: "numeric",
                      month: "long",
                      year: "numeric",
                    })}
                  </dd>
                </div>
                <div>
                  <dt>User ID</dt>
                  <dd className="uid">#{user.id}</dd>
                </div>
                <div>
                  <dt>Member since</dt>
                  <dd>{shortDate(user.created)}</dd>
                </div>
                <div>
                  <dt>Interests</dt>
                  <dd>
                    <Link href="/welcome" className="link">
                      Change your interests
                    </Link>
                  </dd>
                </div>
              </dl>
            )}
          </section>
          <section id="trips" className="card">
            <div className="row-between">
              <h2>My itineraries</h2>
              <Link href="/dashboard" className="btn-ghost">
                Plan a new trip
              </Link>
            </div>
            {trips === null && <p className="muted">Loading</p>}
            {trips?.length === 0 && <p className="muted">No itineraries yet. Every trip you generate is saved here.</p>}
            {trips && trips.length > 0 && (
              <ul className="trip-list">
                {trips.map((t) => (
                  <li key={t.id}>
                    <div>
                      <p className="row-title">
                        {t.origin} to {t.destination}
                        {t.shared && <span className="tag">shared by {t.owner_name}</span>}
                      </p>
                      <p className="muted small">
                        {shortDate(t.start_date)} to {shortDate(t.end_date)}, {t.travellers} traveller
                        {t.travellers > 1 ? "s" : ""}, {rupees(t.total_cost)}. Saved {shortDate(t.updated)}
                      </p>
                    </div>
                    <div className="trip-actions">
                      <Link href={`/dashboard?trip=${t.id}`} className="btn-secondary small-btn">
                        Open
                      </Link>
                      {!t.shared && (
                        <button type="button" className="link small" onClick={() => remove(t)}>
                          Delete
                        </button>
                      )}
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </section>
          <section id="password" className="card">
            <h2>Change password</h2>
            <form className="stack narrow" onSubmit={change}>
              <label>
                <span className="label">Current password</span>
                <input
                  type="password"
                  autoComplete="current-password"
                  required
                  value={current}
                  onChange={(e) => setCurrent(e.target.value)}
                />
              </label>
              <label>
                <span className="label">New password</span>
                <input
                  type="password"
                  autoComplete="new-password"
                  required
                  value={next}
                  onChange={(e) => setNext(e.target.value)}
                />
              </label>
              <p className="hint">
                At least 8 characters, with a letter and a number. Forgot it? Sign out and choose Forgot password.
              </p>
              {msg && (
                <p className={msg.ok ? "notice" : "error"} role="status">
                  {msg.text}
                </p>
              )}
              <button className="btn-primary" disabled={busy}>
                {busy ? "Saving" : "Change password"}
              </button>
            </form>
          </section>
          <section id="help" className="card">
            <h2>Help center</h2>
            <div className="faq">
              {FAQ.map(([q, a]) => (
                <details key={q}>
                  <summary>{q}</summary>
                  <p>{a}</p>
                </details>
              ))}
            </div>
          </section>
        </div>
      </main>
    </div>
  );
}

"use client";
// join a friend's itinerary from an invite link
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import TopBar from "@/components/TopBar";
import { AuthError, acceptInvite, getInvite, type InvitePreview } from "@/lib/api";
import { getSession, type User } from "@/lib/auth";
import { shortDate } from "@/lib/format";

export default function Join() {
  const router = useRouter();
  const { token } = useParams<{ token: string }>();
  const [invite, setInvite] = useState<InvitePreview | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [checked, setChecked] = useState(false);
  const [user, setUser] = useState<User | null>(null);
  useEffect(() => {
    const s = getSession();
    if (!s) router.replace(`/login?next=/join/${encodeURIComponent(token)}`);
    else {
      setUser(s.user);
      setChecked(true);
    }
  }, [router, token]);
  useEffect(() => {
    if (!checked) return;
    getInvite(token)
      .then(setInvite)
      .catch((e) => {
        if (e instanceof AuthError) router.replace(`/login?next=/join/${encodeURIComponent(token)}`);
        else setError((e as Error).message);
      });
  }, [checked, token, router]);
  async function join() {
    setBusy(true);
    try {
      const { trip_id } = await acceptInvite(token);
      router.replace(`/dashboard?trip=${trip_id}`);
    } catch (e) {
      setError((e as Error).message);
      setBusy(false);
    }
  }
  return (
    <div className="page">
      <TopBar user={user} />
      <main className="column narrow">
        <section className="card join">
          {error && (
            <>
              <h1>This link does not work</h1>
              <p className="error" role="alert">
                {error}
              </p>
              <Link href="/dashboard" className="btn-secondary">
                Plan your own trip
              </Link>
            </>
          )}
          {!error && !invite && <p className="muted">Opening the invite</p>}
          {invite && (
            <>
              <p className="kicker">{invite.invited_by} invited you</p>
              <h1>
                {invite.origin} to {invite.destination}
              </h1>
              <p className="muted">
                {shortDate(invite.start_date)} to {shortDate(invite.end_date)}
              </p>
              <p>Already going: {invite.members.join(", ")}</p>
              {invite.joined ? (
                <Link href={`/dashboard?trip=${invite.trip_id}`} className="btn-primary">
                  You are in, open the itinerary
                </Link>
              ) : (
                <button type="button" className="btn-primary" disabled={busy} onClick={join}>
                  {busy ? "Joining" : "Join this trip"}
                </button>
              )}
              <p className="muted small">
                Everyone on the trip can see the plan, change it and regenerate it. You can leave any time.
              </p>
            </>
          )}
        </section>
      </main>
    </div>
  );
}

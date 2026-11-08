"use client";
// travel with friends: invite by link or Gmail, see who is on the trip
import { useEffect, useState } from "react";
import { AuthError, getTrip, inviteFriends, removeMember, type Member } from "@/lib/api";
import type { User } from "@/lib/auth";

type Props = {
  tripId: number;
  route: string;
  dates: string;
  user: User | null;
  onAuthError: () => void;
  onLeft: () => void;
};

export default function Friends({ tripId, route, dates, user, onAuthError, onLeft }: Props) {
  const [members, setMembers] = useState<Member[]>([]);
  const [link, setLink] = useState("");
  const [days, setDays] = useState(7);
  const [copied, setCopied] = useState(false);
  const [error, setError] = useState("");
  useEffect(() => {
    getTrip(tripId)
      .then((t) => setMembers(t.members))
      .catch((e) => e instanceof AuthError && onAuthError());
  }, [tripId, onAuthError]);
  const owner = members.find((m) => m.role === "owner");
  const isOwner = !!user && owner?.id === user.id;
  async function makeLink() {
    setError("");
    try {
      const inv = await inviteFriends(tripId);
      setLink(`${window.location.origin}/join/${inv.token}`);
      setDays(inv.days);
    } catch (e) {
      if (e instanceof AuthError) return onAuthError();
      setError((e as Error).message);
    }
  }
  async function copy() {
    try {
      await navigator.clipboard.writeText(link);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      setError("Copy did not work, select the link and copy it yourself.");
    }
  }
  async function remove(m: Member) {
    try {
      await removeMember(tripId, m.id);
      if (m.id === user?.id) return onLeft();
      setMembers((all) => all.filter((x) => x.id !== m.id));
    } catch (e) {
      setError((e as Error).message);
    }
  }
  const subject = `Join my trip: ${route}`;
  const body = `Hi! I am planning ${route} (${dates}) on Safarnama. Join the itinerary so we can plan it together:\n\n${link}\n\nThe link works for ${days} days.`;
  const gmail = `https://mail.google.com/mail/?view=cm&fs=1&su=${encodeURIComponent(subject)}&body=${encodeURIComponent(body)}`;
  const mail = `mailto:?subject=${encodeURIComponent(subject)}&body=${encodeURIComponent(body)}`;
  return (
    <section className="friends">
      <h3>Travelling together</h3>
      <ul className="people">
        {members.map((m) => (
          <li key={m.id}>
            <span className="avatar" aria-hidden="true">
              {m.name.charAt(0).toUpperCase()}
            </span>
            <span>
              {m.name}
              {m.id === user?.id ? " (you)" : ""}
              <span className="muted small"> {m.role === "owner" ? "planner" : "friend"}</span>
            </span>
            {m.role === "member" && (isOwner || m.id === user?.id) && (
              <button type="button" className="link small" onClick={() => remove(m)}>
                {m.id === user?.id ? "Leave" : "Remove"}
              </button>
            )}
          </li>
        ))}
      </ul>
      <p className="muted small">Friends who join can see this itinerary, chat with it and regenerate it with you.</p>
      {!link ? (
        <button type="button" className="btn-secondary" onClick={makeLink}>
          Invite friends
        </button>
      ) : (
        <div className="invite">
          <label>
            <span className="label">Invite link, works for {days} days</span>
            <input readOnly value={link} onFocus={(e) => e.target.select()} />
          </label>
          <div className="actions-row">
            <a className="btn-primary" href={gmail} target="_blank" rel="noreferrer">
              Send with Gmail
            </a>
            <button type="button" className="btn-secondary" onClick={copy}>
              {copied ? "Copied" : "Copy link"}
            </button>
            <a className="btn-ghost" href={mail}>
              Other email app
            </a>
          </div>
        </div>
      )}
      {error && (
        <p className="error" role="alert">
          {error.charAt(0).toUpperCase() + error.slice(1)}
        </p>
      )}
    </section>
  );
}

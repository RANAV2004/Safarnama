"use client";
// trip viewer
import { useEffect, useState } from "react";
import { getTrip, type Plan, type TripSummary } from "@/lib/api";
import { clock, rupees, shortDate } from "@/lib/format";

export default function TripViewer({ id, onClose }: { id: number; onClose: () => void }) {
  const [trip, setTrip] = useState<(TripSummary & { plan: Plan }) | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    getTrip(id)
      .then(setTrip)
      .catch((e) => setError((e as Error).message));
    const esc = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    document.addEventListener("keydown", esc);
    return () => document.removeEventListener("keydown", esc);
  }, [id, onClose]);
  const p = trip?.plan;
  return (
    <div className="overlay" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div className="viewer card" role="dialog" aria-modal="true" aria-label="Itinerary">
        <div className="row-between">
          <h2>{p ? `${p.request.origin} to ${p.request.destination}` : "Itinerary"}</h2>
          <button type="button" className="btn-ghost" onClick={onClose}>
            Close
          </button>
        </div>
        {error && <p className="error">{error}</p>}
        {!p && !error && <p className="muted">Loading</p>}
        {p && trip && (
          <>
            <p className="muted">
              Itinerary #{trip.id} by {trip.user_id ? `user #${trip.user_id}` : "you"}.{" "}
              {shortDate(p.request.start_date)} to {shortDate(p.request.end_date)}, {p.request.travellers} traveller
              {p.request.travellers > 1 ? "s" : ""}. Total {rupees(p.total_cost)} of {rupees(p.request.budget_inr)}.
              Saved {shortDate(trip.updated)}.
            </p>
            <ul className="notes">
              {p.outbound && (
                <li>
                  Going: {p.outbound.mode} by {p.outbound.provider}, {shortDate(p.outbound.depart_at)}{" "}
                  {clock(p.outbound.depart_at)}, {rupees(p.outbound.price_inr)}
                </li>
              )}
              {p.return && (
                <li>
                  Coming back: {p.return.mode} by {p.return.provider}, {shortDate(p.return.depart_at)}{" "}
                  {clock(p.return.depart_at)}, {rupees(p.return.price_inr)}
                </li>
              )}
              {p.stay && (
                <li>
                  Staying at {p.stay.name}, {rupees(p.stay.price_per_night_inr)} a night
                </li>
              )}
            </ul>
            {p.days.map((d, i) => (
              <div key={d.date} className="day">
                <p className="day-title">
                  <strong>Day {i + 1}</strong> <span className="muted">{shortDate(d.date)}</span>
                </p>
                <ul className="timeline">
                  {d.items.map((it, j) => (
                    <li key={j} className={it.kind}>
                      <time>{it.start === it.end ? it.start : `${it.start} to ${it.end}`}</time>
                      <span className="what">{it.title}</span>
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </>
        )}
      </div>
    </div>
  );
}

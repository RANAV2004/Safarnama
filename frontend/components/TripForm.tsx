"use client";
// trip form
import { useMemo } from "react";
import type { Route, TripRequest } from "@/lib/api";
import { addDays, nightsBetween, rupees } from "@/lib/format";
const INTERESTS = ["beach", "history", "nature", "culture", "shopping"];
type Props = {
  routes: Route[];
  value: TripRequest;
  onChange: (v: TripRequest) => void;
  onSubmit: () => void;
  busy: boolean;
  hasPlan: boolean;
};

export default function TripForm({ routes, value, onChange, onSubmit, busy, hasPlan }: Props) {
  const origins = useMemo(() => [...new Set(routes.map((r) => r.from))].sort(), [routes]);
  const destinations = routes.filter((r) => r.from === value.origin).map((r) => r.to);
  const nights = nightsBetween(value.start_date, value.end_date);
  const set = (patch: Partial<TripRequest>) => onChange({ ...value, ...patch });
  function pickOrigin(origin: string) {
    const options = routes.filter((r) => r.from === origin).map((r) => r.to);
    set({ origin, destination: options.includes(value.destination) ? value.destination : (options[0] ?? "") });
  }
  function toggle(p: string) {
    set({
      preferences: value.preferences.includes(p) ? value.preferences.filter((x) => x !== p) : [...value.preferences, p],
    });
  }
  return (
    <form
      className="card trip-form"
      onSubmit={(e) => {
        e.preventDefault();
        onSubmit();
      }}
    >
      <h2>Plan a trip</h2>
      <div className="route-pick">
        <label>
          <span className="label">From</span>
          <select value={value.origin} onChange={(e) => pickOrigin(e.target.value)}>
            {origins.map((o) => (
              <option key={o}>{o}</option>
            ))}
          </select>
        </label>
        <span className="route-dots" aria-hidden="true" />
        <label>
          <span className="label">To</span>
          <select value={value.destination} onChange={(e) => set({ destination: e.target.value })}>
            {destinations.map((d) => (
              <option key={d}>{d}</option>
            ))}
          </select>
        </label>
      </div>
      <div className="grid-2">
        <label>
          <span className="label">Start</span>
          <input
            type="date"
            value={value.start_date}
            required
            onChange={(e) =>
              set({
                start_date: e.target.value,
                end_date: e.target.value > value.end_date ? e.target.value : value.end_date,
              })
            }
          />
        </label>
        <label>
          <span className="label">End</span>
          <input
            type="date"
            value={value.end_date}
            min={value.start_date}
            max={addDays(value.start_date, 14)}
            required
            onChange={(e) => set({ end_date: e.target.value })}
          />
        </label>
      </div>
      <p className="hint">
        {nights === 0 ? "Day trip, no hotel needed" : `${nights} night${nights > 1 ? "s" : ""}, ${nights + 1} days`}
      </p>
      <div className="grid-2">
        <label>
          <span className="label">Budget in rupees</span>
          <input
            type="number"
            inputMode="numeric"
            min={500}
            step={100}
            value={value.budget_inr || ""}
            required
            onChange={(e) => set({ budget_inr: Number(e.target.value) })}
          />
        </label>
        <div>
          <span className="label">Travellers</span>
          <div className="stepper">
            <button
              type="button"
              aria-label="Fewer travellers"
              onClick={() => set({ travellers: Math.max(1, value.travellers - 1) })}
            >
              −
            </button>
            <output aria-live="polite">{value.travellers}</output>
            <button
              type="button"
              aria-label="More travellers"
              onClick={() => set({ travellers: Math.min(10, value.travellers + 1) })}
            >
              +
            </button>
          </div>
        </div>
      </div>
      <p className="hint">
        {rupees(Math.round((value.budget_inr || 0) / Math.max(1, value.travellers)))} per person for the whole trip
      </p>
      <fieldset>
        <legend className="label">What do you enjoy</legend>
        <div className="chips">
          {INTERESTS.map((p) => (
            <button
              type="button"
              key={p}
              className="chip"
              aria-pressed={value.preferences.includes(p)}
              onClick={() => toggle(p)}
            >
              {p}
            </button>
          ))}
        </div>
      </fieldset>
      <label>
        <span className="label">Anything else</span>
        <textarea
          rows={2}
          maxLength={300}
          value={value.note}
          onChange={(e) => set({ note: e.target.value })}
          placeholder="For example: a quiet hotel, more time at the beach"
        />
        <span className="hint">Read by the AI agents when a model is connected</span>
      </label>
      <button className="btn-primary big" disabled={busy || !value.destination}>
        {busy ? "Your agents are planning" : hasPlan ? "Regenerate itinerary" : "Generate itinerary"}
      </button>
    </form>
  );
}

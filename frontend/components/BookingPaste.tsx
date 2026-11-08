"use client";
// paste a flight, train or bus booking and plan the trip around it
import { useState } from "react";
import { readBooking, type Booking, type MyJourney } from "@/lib/api";
import { clock, shortDate } from "@/lib/format";

type Mode = MyJourney["mode"];
const MODES: [Mode, string, string, string][] = [
  [
    "flight",
    "Flight",
    "IndiGo 6E 5321 BOM 06:10 to GOI 07:25, 12 Dec 2026",
    "Airline name or code, flight number, airports, date and times",
  ],
  [
    "train",
    "Train",
    "Train No./Name: 10103/MANDOVI EXP  From: MUMBAI CSMT (CSMT)  To: MADGAON (MAO)  Departure 07:10 12-Dec-2026  Arrival 19:40",
    "From your IRCTC e-ticket: train number and name, stations, date, departure and arrival",
  ],
  [
    "bus",
    "Bus",
    "Travels: Neeta Tours and Travels  From: Mumbai  To: Goa  Journey Date: 12 Dec 2026  Departure Time: 20:00  Arrival Time: 13 Dec 08:30",
    "From your redBus or operator ticket: operator, cities, date, departure and arrival",
  ],
];
const NAME_LABEL: Record<Mode, string> = { flight: "Airline", train: "Train name", bus: "Bus operator" };
const NUMBER_LABEL: Record<Mode, string> = {
  flight: "Flight number",
  train: "Train number",
  bus: "Ticket or bus number",
};

type Props = {
  origin: string;
  destination: string;
  onUse: (leg: "my_outbound" | "my_return", j: MyJourney) => void;
  onClose: () => void;
};

export default function BookingPaste({ origin, destination, onUse, onClose }: Props) {
  const [text, setText] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [found, setFound] = useState<Booking | null>(null);
  const [leg, setLeg] = useState<"my_outbound" | "my_return">("my_outbound");
  const [mode, setMode] = useState<Mode>("flight");
  const current = MODES.find((m) => m[0] === mode)!;
  async function read(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const b = await readBooking(text, mode);
      setFound(b);
      setLeg(b.from_city === destination || b.to_city === origin ? "my_return" : "my_outbound");
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }
  const wrongRoute =
    found &&
    ((found.from_city && ![origin, destination].includes(found.from_city)) ||
      (found.to_city && ![origin, destination].includes(found.to_city)));
  return (
    <div className="booking">
      {!found ? (
        <form onSubmit={read} className="stack">
          <div className="tabs mode-tabs" role="tablist" aria-label="How you are travelling">
            {MODES.map(([id, label]) => (
              <button key={id} type="button" role="tab" aria-selected={mode === id} onClick={() => setMode(id)}>
                {label}
              </button>
            ))}
          </div>
          <label>
            <span className="label">Paste your {current[1].toLowerCase()} booking</span>
            <textarea
              rows={3}
              maxLength={2000}
              value={text}
              onChange={(e) => setText(e.target.value)}
              placeholder={`For example: ${current[2]}`}
            />
          </label>
          <p className="hint">{current[3]}. Copying the whole ticket or email is fine.</p>
          {error && (
            <p className="error" role="alert">
              {error.charAt(0).toUpperCase() + error.slice(1)}
            </p>
          )}
          <div className="actions-row">
            <button className="btn-primary" disabled={busy || !text.trim()}>
              {busy ? "Reading" : "Read my booking"}
            </button>
            <button type="button" className="btn-ghost" onClick={onClose}>
              Cancel
            </button>
          </div>
        </form>
      ) : (
        <div className="stack">
          <p>
            <strong>
              {found.provider} {found.number}
            </strong>
            {found.from_city && found.to_city ? `, ${found.from_city} to ${found.to_city}` : ""}
          </p>
          <div className="booking-grid">
            <label>
              <span className="label">Travelling by</span>
              <select value={found.mode} onChange={(e) => setFound({ ...found, mode: e.target.value as Mode })}>
                <option value="flight">Flight</option>
                <option value="train">Train</option>
                <option value="bus">Bus</option>
              </select>
            </label>
            <label>
              <span className="label">{NAME_LABEL[found.mode]}</span>
              <input
                value={found.provider}
                maxLength={60}
                onChange={(e) => setFound({ ...found, provider: e.target.value })}
              />
            </label>
            <label>
              <span className="label">{NUMBER_LABEL[found.mode]}</span>
              <input
                value={found.number}
                maxLength={20}
                onChange={(e) => setFound({ ...found, number: e.target.value })}
              />
            </label>
            <label>
              <span className="label">Leaves</span>
              <input
                type="datetime-local"
                value={found.depart_at.slice(0, 16)}
                onChange={(e) => setFound({ ...found, depart_at: e.target.value })}
              />
            </label>
            <label>
              <span className="label">Arrives</span>
              <input
                type="datetime-local"
                value={found.arrive_at.slice(0, 16)}
                onChange={(e) => setFound({ ...found, arrive_at: e.target.value })}
              />
            </label>
            <label>
              <span className="label">Price paid, all travellers</span>
              <input
                type="number"
                min={0}
                inputMode="numeric"
                value={found.price_inr}
                onChange={(e) => setFound({ ...found, price_inr: Math.max(0, Number(e.target.value) || 0) })}
              />
            </label>
            <label>
              <span className="label">This journey is</span>
              <select value={leg} onChange={(e) => setLeg(e.target.value as typeof leg)}>
                <option value="my_outbound">Getting there</option>
                <option value="my_return">Coming back</option>
              </select>
            </label>
          </div>
          {wrongRoute && (
            <p className="notice">
              This booking is for {found.from_city} to {found.to_city}, but your trip is {origin} to {destination}.
              Check it is the right ticket.
            </p>
          )}
          <p className="muted small">
            {leg === "my_outbound"
              ? `Your day 1 will start when you land at ${clock(found.arrive_at)} on ${shortDate(found.arrive_at)}.`
              : `Your last day will end in time for your ${clock(found.depart_at)} departure on ${shortDate(found.depart_at)}.`}
          </p>
          <div className="actions-row">
            <button
              type="button"
              className="btn-primary"
              onClick={() =>
                onUse(leg, {
                  mode: found.mode,
                  provider: found.provider,
                  number: found.number,
                  depart_at: found.depart_at,
                  arrive_at: found.arrive_at,
                  price_inr: found.price_inr,
                })
              }
            >
              Use this journey
            </button>
            <button type="button" className="btn-ghost" onClick={() => setFound(null)}>
              Paste again
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

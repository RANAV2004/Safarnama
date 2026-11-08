"use client";
// itinerary
import { useCallback, useState } from "react";
import type { Card, MyJourney, Pins, Plan, Stay, Transport } from "@/lib/api";
import { clock, rupees, shortDate, toRupeeSign } from "@/lib/format";
import AgentLog from "./AgentLog";
import BookingPaste from "./BookingPaste";
import Photo from "./Photo";
import PlaceSheet, { KIND_NAMES } from "./PlaceSheet";
import StopsOnTheWay from "./StopsOnTheWay";
type Props = {
  plan: Plan;
  pins: Pins;
  setPins: (p: Pins) => void;
  dirty: boolean;
  busy: boolean;
  downloading: boolean;
  onRegenerate: () => void;
  onDownload: () => void;
};
const COSTS = [
  ["transport", "Travel"],
  ["stay", "Stay"],
  ["food", "Food"],
  ["activities", "Entry fees"],
] as const;

function journey(t: Transport) {
  return `${t.mode.charAt(0).toUpperCase() + t.mode.slice(1)}, ${shortDate(t.depart_at)} ${clock(t.depart_at)} to ${t.overnight ? shortDate(t.arrive_at) + " " : ""}${clock(t.arrive_at)}`;
}

function stayLine(s: Stay) {
  return `${s.area ? s.area + ", " : ""}${s.rating ? `rated ${s.rating}, ` : ""}${s.late_checkin ? "24 hour desk" : `desk open until ${s.checkin_until.slice(0, 5)}`}`;
}
type Choice = { id: string; title: string; detail: string; price: string };

function bookedLine(j: MyJourney) {
  const name = [j.provider, j.number].filter(Boolean).join(" ") || j.mode;
  return `${name}, ${shortDate(j.depart_at)} ${clock(j.depart_at)} to ${clock(j.arrive_at)}${j.arrive_at.slice(0, 10) !== j.depart_at.slice(0, 10) ? " next day" : ""}`;
}

function Row({
  label,
  current,
  pendingId,
  choices,
  onPick,
}: {
  label: string;
  current: Choice | null;
  pendingId?: string;
  choices: Choice[];
  onPick: (id: string | undefined) => void;
}) {
  const [open, setOpen] = useState(false);
  if (!current) return null;
  const pending = pendingId && pendingId !== current.id ? choices.find((c) => c.id === pendingId) : undefined;
  const shown = pending ?? current;
  return (
    <div className={`row-item ${pending ? "changed" : ""}`}>
      <div className="row-main">
        <p className="label">
          {label}
          {pending && <span className="tag">new choice</span>}
        </p>
        <p className="row-title">{shown.title}</p>
        <p className="muted">{shown.detail}</p>
      </div>
      <p className="row-price">{shown.price}</p>
      <button type="button" className="link" aria-expanded={open} onClick={() => setOpen(!open)}>
        {open ? "Close" : "Change"}
      </button>
      {open && (
        <ul className="choices">
          {choices.map((c) => (
            <li key={c.id}>
              <label>
                <input
                  type="radio"
                  name={label}
                  checked={shown.id === c.id}
                  onChange={() => {
                    onPick(c.id === current.id ? undefined : c.id);
                    setOpen(false);
                  }}
                />
                <span>
                  <strong>{c.title}</strong>
                  <br />
                  <span className="muted">{c.detail}</span>
                </span>
                <span className="choice-price">{c.price}</span>
              </label>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export default function Itinerary({ plan, pins, setPins, dirty, busy, downloading, onRegenerate, onDownload }: Props) {
  const r = plan.request;
  const nights = plan.days.length - 1;
  const inPlan = new Set(plan.places.map((p) => p.id));
  const addable = plan.options.places.filter(
    (p) => !inPlan.has(p.id) && !pins.include_places.includes(p.id) && !pins.exclude_places.includes(p.id),
  );
  const removedEarlier = plan.options.places.filter((p) => pins.exclude_places.includes(p.id) && !inPlan.has(p.id));
  const adding = plan.options.places.filter((p) => pins.include_places.includes(p.id) && !inPlan.has(p.id));
  const tChoice = (t: Transport): Choice => ({
    id: t.id,
    title: t.provider,
    detail: journey(t),
    price: rupees(t.price_inr),
  });
  const sChoice = (s: Stay): Choice => ({
    id: s.id,
    title: s.name,
    detail: stayLine(s),
    price: `${rupees(s.price_per_night_inr)} a night`,
  });
  function removePlace(id: string) {
    setPins({
      ...pins,
      include_places: pins.include_places.filter((x) => x !== id),
      exclude_places: [...pins.exclude_places, id],
    });
  }
  function restorePlace(id: string) {
    setPins({ ...pins, exclude_places: pins.exclude_places.filter((x) => x !== id) });
  }
  const [open, setOpen] = useState<Card | null>(null);
  const [pasting, setPasting] = useState(false);
  const close = useCallback(() => setOpen(null), []);
  function cardFor(id: string): Card | null {
    const d = plan.details?.[id];
    if (d) return d;
    const p = plan.options.places.find((x) => x.id === id);
    return p
      ? { id, name: p.name, kind: "attraction", category: p.category, text: "", lat: 0, lng: 0, maps_url: "" }
      : null;
  }
  const meals = new Map((plan.meals ?? []).map((m) => [m.date, m.picks]));
  const byRoad = [plan.outbound?.mode, plan.return?.mode].includes("bus");
  const booked = (["my_outbound", "my_return"] as const).filter((k) => pins[k]);
  return (
    <article className="card itinerary">
      <header className="it-head">
        <div>
          <h2>
            {r.origin} to {r.destination}
          </h2>
          <p className="muted">
            {shortDate(r.start_date)} to {shortDate(r.end_date)}, {r.travellers} traveller{r.travellers > 1 ? "s" : ""}
            {nights > 0 ? `, ${nights} night${nights > 1 ? "s" : ""}` : ", day trip"}
          </p>
        </div>
        <div className="total">
          <p className="total-number">{rupees(plan.total_cost)}</p>
          <p className={plan.over_budget_by > 0 ? "over" : "ok"}>
            {plan.over_budget_by > 0
              ? `${rupees(plan.over_budget_by)} over budget`
              : `${rupees(r.budget_inr - plan.total_cost)} left of ${rupees(r.budget_inr)}`}
          </p>
        </div>
      </header>
      <dl className="costs">
        {COSTS.map(([k, label]) => (
          <div key={k}>
            <dt>{label}</dt>
            <dd>{rupees(plan.breakdown[k] ?? 0)}</dd>
          </div>
        ))}
      </dl>
      <section>
        <h3>Travel and stay</h3>
        <Row
          label="Getting there"
          current={plan.outbound && tChoice(plan.outbound)}
          pendingId={pins.outbound_id}
          choices={plan.options.outbound.map(tChoice)}
          onPick={(id) => setPins({ ...pins, outbound_id: id })}
        />
        <Row
          label="Coming back"
          current={plan.return && tChoice(plan.return)}
          pendingId={pins.return_id}
          choices={plan.options.return.map(tChoice)}
          onPick={(id) => setPins({ ...pins, return_id: id })}
        />
        <Row
          label="Staying at"
          current={plan.stay && sChoice(plan.stay)}
          pendingId={pins.stay_id}
          choices={plan.options.stays.map(sChoice)}
          onPick={(id) => setPins({ ...pins, stay_id: id })}
        />
        {booked.map((k) => (
          <p key={k} className="pending-line">
            <span className="tag">booked</span> {k === "my_outbound" ? "Getting there" : "Coming back"}:{" "}
            {bookedLine(pins[k]!)}{" "}
            <button type="button" className="link small" onClick={() => setPins({ ...pins, [k]: null })}>
              Remove
            </button>
          </p>
        ))}
        {pasting ? (
          <BookingPaste
            origin={r.origin}
            destination={r.destination}
            onClose={() => setPasting(false)}
            onUse={(leg, j) => {
              setPins({
                ...pins,
                [leg]: j,
                ...(leg === "my_outbound" ? { outbound_id: undefined } : { return_id: undefined }),
              });
              setPasting(false);
            }}
          />
        ) : (
          <button type="button" className="link small" onClick={() => setPasting(true)}>
            Already booked a flight, train or bus? Paste your ticket
          </button>
        )}
      </section>
      {plan.stops && plan.stops.stops.length > 0 && (
        <StopsOnTheWay route={plan.stops} byRoad={byRoad} onOpen={setOpen} />
      )}
      <section>
        <h3>Day by day</h3>
        {plan.days.map((d, i) => (
          <div key={d.date} className="day">
            <p className="day-title">
              <strong>Day {i + 1}</strong> <span className="muted">{shortDate(d.date)}</span>
            </p>
            <ul className="timeline">
              {d.items.map((it, j) => {
                const removed = it.place_id !== null && pins.exclude_places.includes(it.place_id);
                const card = it.kind === "place" && it.place_id ? cardFor(it.place_id) : null;
                return (
                  <li key={j} className={`${it.kind} ${removed ? "removed" : ""}`}>
                    <time>{it.start === it.end ? it.start : `${it.start} to ${it.end}`}</time>
                    {card ? (
                      <button type="button" className="what place-row" onClick={() => card.lat && setOpen(card)}>
                        <Photo id={card.id} kind={card.category} name={card.name} />
                        <span>
                          <strong>{it.title}</strong>
                          {it.cost_inr > 0 && <span className="muted"> {rupees(it.cost_inr)}</span>}
                          {card.text && <span className="blurb">{card.text}</span>}
                        </span>
                      </button>
                    ) : (
                      <span className="what">{it.title}</span>
                    )}
                    {it.kind === "place" && it.place_id && (
                      <button
                        type="button"
                        className="link small"
                        onClick={() => (removed ? restorePlace(it.place_id!) : removePlace(it.place_id!))}
                      >
                        {removed ? "Undo" : "Remove"}
                      </button>
                    )}
                  </li>
                );
              })}
            </ul>
            {meals.get(d.date) && (
              <div className="eat">
                <p className="label">Eat nearby</p>
                <div className="eat-row">
                  {meals.get(d.date)!.map((m) => (
                    <button key={m.id} type="button" className="eat-chip" onClick={() => setOpen(m)}>
                      <Photo id={m.id} kind={m.kind} name={m.name} />
                      <span>
                        <span className="kicker">
                          {KIND_NAMES[m.kind]} · {m.km} km
                        </span>
                        <strong>{m.name}</strong>
                        {m.must_try && <span className="muted small">Try the {m.must_try.toLowerCase()}</span>}
                      </span>
                    </button>
                  ))}
                </div>
              </div>
            )}
          </div>
        ))}
        <div className="add-place">
          <label>
            <span className="label">Add a place</span>
            <select
              value=""
              onChange={(e) =>
                e.target.value && setPins({ ...pins, include_places: [...pins.include_places, e.target.value] })
              }
            >
              <option value="">Choose a place to add</option>
              {addable.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                  {p.entry_fee_inr ? `, ${rupees(p.entry_fee_inr)} entry` : ", free"}
                </option>
              ))}
            </select>
          </label>
          {adding.map((p) => (
            <p key={p.id} className="pending-line">
              Will add {p.name}{" "}
              <button
                type="button"
                className="link small"
                onClick={() => setPins({ ...pins, include_places: pins.include_places.filter((x) => x !== p.id) })}
              >
                Undo
              </button>
            </p>
          ))}
          {removedEarlier.map((p) => (
            <p key={p.id} className="pending-line muted">
              Removed {p.name}{" "}
              <button type="button" className="link small" onClick={() => restorePlace(p.id)}>
                Bring back
              </button>
            </p>
          ))}
        </div>
      </section>
      {plan.notes.length > 0 && (
        <section>
          <h3>Good to know</h3>
          <ul className="notes">
            {plan.notes.map((n, i) => (
              <li key={i}>{toRupeeSign(n.charAt(0).toUpperCase() + n.slice(1))}</li>
            ))}
          </ul>
        </section>
      )}
      <details className="how">
        <summary>See how the agents planned this</summary>
        <AgentLog events={plan.trace} />
      </details>
      <div className="actions">
        {dirty && <p className="hint">You have changes. Regenerate so the agents can plan around them.</p>}
        <div className="actions-row">
          <button type="button" className="btn-primary" disabled={busy} onClick={onRegenerate}>
            {busy ? "Regenerating" : dirty ? "Regenerate with my changes" : "Regenerate"}
          </button>
          <button type="button" className="btn-secondary" disabled={downloading} onClick={onDownload}>
            {downloading ? "Preparing PDF" : "Download PDF"}
          </button>
        </div>
      </div>
      <p className="muted small">Prices and timings come from sample data. Check them before you book.</p>
      {open && <PlaceSheet card={open} onClose={close} />}
    </article>
  );
}

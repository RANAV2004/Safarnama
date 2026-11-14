"use client";
// the day by day plan: a cover for each day, then a timeline of travel, places and meals
import type { Card, DayPlan, Meal, PlanItem } from "@/lib/api";
import { rupees, shortDate } from "@/lib/format";
import Photo from "./Photo";

type Props = {
  days: DayPlan[];
  destination: string;
  meals: Map<string, Meal["picks"]>;
  excluded: string[];
  cardFor: (id: string) => Card | null;
  onOpen: (c: Card) => void;
  onRemove: (id: string) => void;
  onRestore: (id: string) => void;
};

const THEMES: Record<string, string> = {
  beach: "Beaches",
  history: "History",
  nature: "Nature",
  culture: "Culture",
  shopping: "Markets",
  science: "Science",
  sightseeing: "Sightseeing",
};
const ICONS: Record<string, string> = {
  train:
    "M6 3h12a2 2 0 0 1 2 2v10a3 3 0 0 1-3 3H7a3 3 0 0 1-3-3V5a2 2 0 0 1 2-2zM4 11h16M8 21l2-3M16 21l-2-3M8 14.5h.01M16 14.5h.01",
  flight: "M10 3.5a1.5 1.5 0 0 1 3 0V9l8 5v2l-8-2.5V18l2.5 2v1.5L12 20.5 8.5 21.5V20l2.5-2v-4.5L3 16v-2l7-5z",
  bus: "M5 4h14a1 1 0 0 1 1 1v12a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V5a1 1 0 0 1 1-1zM4 11h16M7 21v-2M17 21v-2M7.5 15h.01M16.5 15h.01",
  checkin: "M3 18V8M3 14h18v4M21 14v-3a3 3 0 0 0-3-3h-7v6M7 11.5a1.5 1.5 0 1 0 0-.01",
  free: "M12 4V2M12 22v-2M4 12H2M22 12h-2M5.6 5.6 4.2 4.2M19.8 19.8l-1.4-1.4M5.6 18.4l-1.4 1.4M19.8 4.2l-1.4 1.4M12 7a5 5 0 1 0 0 10 5 5 0 0 0 0-10z",
  meal: "M7 3v8M5 3v4a2 2 0 0 0 4 0V3M7 11v10M17 3c-2 0-3 2-3 5s1 4 3 4v9",
  cafe: "M4 9h13v4a5 5 0 0 1-5 5H9a5 5 0 0 1-5-5V9M17 10h1a2 2 0 0 1 0 4h-1M8 3c0 2 1 2 1 4M12 3c0 2 1 2 1 4",
};

function Icon({ name }: { name: string }) {
  return (
    <svg
      viewBox="0 0 24 24"
      width="18"
      height="18"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.7"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d={ICONS[name] ?? ICONS.free} />
    </svg>
  );
}

function minutes(t: string) {
  const [h, m] = t.split(":").map(Number);
  return h * 60 + m;
}

function duration(it: PlanItem) {
  const m = minutes(it.end) - minutes(it.start);
  if (m <= 0) return "";
  return m % 60 ? `${Math.floor(m / 60) ? `${Math.floor(m / 60)} h ` : ""}${m % 60} min` : `${m / 60} h`;
}

function travelIcon(title: string) {
  const t = title.toLowerCase();
  return t.includes("flight") ? "flight" : t.includes("bus") ? "bus" : "train";
}

function theme(cards: Card[], first: boolean, last: boolean, destination: string) {
  const names = [...new Set(cards.map((c) => THEMES[c.category] ?? "Sightseeing"))].slice(0, 2);
  const base = names.length ? names.join(" and ") : `Free time in ${destination}`;
  if (first) return names.length ? `Arrival, then ${base.toLowerCase()}` : `Arrive in ${destination}`;
  if (last) return names.length ? `${base}, then home` : "Heading home";
  return base;
}

type Row =
  | { type: "item"; item: PlanItem; index: number }
  | { type: "meal"; pick: Meal["picks"][number]; label: string };

function rows(day: DayPlan, picks: Meal["picks"] | undefined): Row[] {
  const out: Row[] = day.items.map((item, index) => ({ type: "item", item, index }));
  const places = out.filter((r) => r.type === "item" && r.item.kind === "place").length;
  const food = (picks ?? []).find((p) => p.kind === "restaurant");
  const cafe = (picks ?? []).find((p) => p.kind === "cafe");
  const afterPlace = (n: number) => {
    let seen = 0;
    return out.findIndex((r) => r.type === "item" && r.item.kind === "place" && ++seen === n) + 1;
  };
  if (food) {
    const at = places >= 2 ? afterPlace(1) : out.length;
    const lunch = places >= 2 && at > 0;
    out.splice(lunch ? at : out.length, 0, {
      type: "meal",
      pick: food,
      label: lunch ? "Lunch nearby" : "Dinner nearby",
    });
  }
  if (cafe) {
    const at = places >= 3 ? afterPlace(2) : out.length;
    out.splice(at > 0 ? at : out.length, 0, { type: "meal", pick: cafe, label: "Coffee break nearby" });
  }
  const last = out[out.length - 1];
  const leaving = day.items.findIndex((it) => it.kind === "travel" && it.title.startsWith("Leave"));
  if (leaving >= 0 && last?.type === "meal") {
    const idx = out.findIndex((r) => r.type === "item" && r.index === leaving);
    const moved = out.splice(idx, 1);
    out.push(...moved);
  }
  return out;
}

export default function DayByDay({ days, destination, meals, excluded, cardFor, onOpen, onRemove, onRestore }: Props) {
  return (
    <section className="days">
      <div className="days-head">
        <h3>Day by day</h3>
        <nav className="day-pills" aria-label="Jump to a day">
          {days.map((d, i) => (
            <a key={d.date} href={`#day-${i + 1}`}>
              <strong>Day {i + 1}</strong>
              <span>{shortDate(d.date)}</span>
            </a>
          ))}
        </nav>
      </div>
      {days.map((d, i) => {
        const cards = d.items
          .filter((it) => it.kind === "place" && it.place_id)
          .map((it) => cardFor(it.place_id!))
          .filter((c): c is Card => !!c);
        const cover = cards.find((c) => c.photo_url) ?? cards[0];
        const fees = d.items.reduce((sum, it) => sum + (it.kind === "place" ? it.cost_inr : 0), 0);
        const facts = [
          shortDate(d.date),
          cards.length ? `${cards.length} place${cards.length > 1 ? "s" : ""}` : "",
          d.km ? `${Math.round(d.km)} km around town` : "",
          fees ? `${rupees(fees)} entry` : "",
        ].filter(Boolean);
        return (
          <article key={d.date} id={`day-${i + 1}`} className="day-card">
            <header className="day-cover">
              {cover ? (
                <Photo id={cover.id} kind={cover.category} name={cover.name} src={cover.photo_url} />
              ) : (
                <div className="day-cover-plain" />
              )}
              <div className="day-cover-text">
                <span className="day-num">Day {i + 1}</span>
                <h4>{theme(cards, i === 0, i === days.length - 1, destination)}</h4>
                <p>{facts.join(" · ")}</p>
              </div>
            </header>
            <ol className="flow">
              {rows(d, meals.get(d.date)).map((r, j, all) => {
                if (r.type === "meal") {
                  const m = r.pick;
                  return (
                    <li key={`m${j}`} className="flow-meal">
                      <span className="flow-dot meal">
                        <Icon name={m.kind === "cafe" ? "cafe" : "meal"} />
                      </span>
                      <button type="button" className="meal-card" onClick={() => onOpen(m)}>
                        <span className="tile-photo">
                          <Photo id={m.id} kind={m.kind} name={m.name} src={m.photo_url} />
                          {m.photo_note && <span className="photo-note">{m.photo_note}</span>}
                        </span>
                        <span className="meal-text">
                          <span className="kicker">
                            {r.label} · {m.km} km
                          </span>
                          <strong>{m.name}</strong>
                          <span className="muted small">
                            {m.must_try ? `Try the ${m.must_try.toLowerCase()}` : m.text}
                          </span>
                        </span>
                      </button>
                    </li>
                  );
                }
                const it = r.item;
                const card = it.kind === "place" && it.place_id ? cardFor(it.place_id) : null;
                if (!card) {
                  const icon = it.kind === "travel" ? travelIcon(it.title) : it.kind;
                  return (
                    <li key={`i${j}`} className={`flow-note ${it.kind}`}>
                      <span className="flow-dot">
                        <Icon name={icon} />
                      </span>
                      <span className="flow-note-text">
                        <time>{it.start === it.end ? it.start : `${it.start} – ${it.end}`}</time>
                        <span>{it.title}</span>
                      </span>
                    </li>
                  );
                }
                const removed = excluded.includes(card.id);
                const facts2 = [
                  card.category && card.category !== "attraction" ? card.category : "",
                  duration(it),
                  it.cost_inr ? `${rupees(it.cost_inr)} entry` : "Free entry",
                ].filter(Boolean);
                return (
                  <li key={`i${j}`} className={`flow-place${removed ? " removed" : ""}`}>
                    <span className="flow-dot place">
                      {all.slice(0, j + 1).filter((x) => x.type === "item" && x.item.kind === "place").length}
                    </span>
                    <div className="place-card">
                      <button
                        type="button"
                        className="place-photo"
                        onClick={() => onOpen(card)}
                        aria-label={`Details of ${card.name}`}
                      >
                        <Photo id={card.id} kind={card.category} name={card.name} src={card.photo_url} />
                        <span className="time-chip">
                          {it.start} – {it.end}
                        </span>
                      </button>
                      <div className="place-body">
                        <span className="kicker">{facts2.join(" · ")}</span>
                        <h5>{card.name}</h5>
                        {card.text && <p className="blurb">{card.text}</p>}
                        <div className="place-actions">
                          <button type="button" className="btn-secondary small-btn" onClick={() => onOpen(card)}>
                            Details and map
                          </button>
                          <a className="link small" href={card.maps_url} target="_blank" rel="noreferrer">
                            Directions
                          </a>
                          <button
                            type="button"
                            className="link small"
                            onClick={() => (removed ? onRestore(card.id) : onRemove(card.id))}
                          >
                            {removed ? "Undo" : "Remove"}
                          </button>
                        </div>
                      </div>
                    </div>
                  </li>
                );
              })}
            </ol>
          </article>
        );
      })}
    </section>
  );
}

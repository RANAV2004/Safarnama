"use client";
// explore a destination: restaurants, attractions, cafes, photo spots, top places and travel information
import { useCallback, useEffect, useState } from "react";
import Photo from "@/components/Photo";
import PlaceSheet from "@/components/PlaceSheet";
import TopBar from "@/components/TopBar";
import { getCities, getCity, type Card, type CityGuide, type CitySummary } from "@/lib/api";
import { useAccount } from "@/lib/useAccount";

const TABS = [
  ["restaurant", "Restaurants"],
  ["attraction", "Attractions"],
  ["cafe", "Cafes"],
  ["photo", "Photo spots"],
] as const;
const INFO_NAMES: Record<string, string> = {
  intro: "Intro",
  understand: "Understand",
  get_in: "Get in",
  get_around: "Get around",
  best_time: "Best time to go",
  stay_safe: "Stay safe",
};
const FILTERS = [
  ["all", "All"],
  ["beach", "Beaches"],
  ["mountains", "Mountains"],
  ["trekking", "Trekking"],
  ["heritage", "Heritage"],
  ["spiritual", "Spiritual"],
  ["nature", "Nature"],
  ["city", "Big cities"],
  ["nepal", "Nepal"],
] as const;
type Tab = (typeof TABS)[number][0];

function CardTile({ card, onOpen }: { card: Card; onOpen: (c: Card) => void }) {
  const kind = card.kind === "attraction" ? card.category : card.kind;
  return (
    <button type="button" className="tile" onClick={() => onOpen(card)}>
      <span className="tile-photo">
        <Photo id={card.id} kind={kind} name={card.name} src={card.photo_url} />
        {card.photo_note && <span className="photo-note">{card.photo_note}</span>}
      </span>
      <span className="tile-text">
        <strong>{card.name}</strong>
        <span className="muted small">
          {[
            card.rating ? `★ ${card.rating}${card.reviews ? ` (${card.reviews.toLocaleString("en-IN")})` : ""}` : "",
            card.area,
            card.price && card.price.length <= 4 ? card.price : "",
            card.must_try && `try the ${card.must_try.toLowerCase()}`,
          ]
            .filter(Boolean)
            .join(" · ") || card.category}
        </span>
        <span className="blurb">{card.text}</span>
      </span>
    </button>
  );
}

export default function Explore() {
  const { user } = useAccount();
  const [cities, setCities] = useState<CitySummary[]>([]);
  const [city, setCity] = useState<CityGuide | null>(null);
  const [tab, setTab] = useState<Tab>("restaurant");
  const [info, setInfo] = useState<string>("intro");
  const [filter, setFilter] = useState<string>("all");
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState<Card | null>(null);
  const [error, setError] = useState("");
  const close = useCallback(() => setOpen(null), []);
  const q = query.trim().toLowerCase();
  const shown = cities.filter(
    (c) =>
      (filter === "all" || c.tags.includes(filter)) &&
      (!q || c.name.toLowerCase().includes(q) || c.tagline.toLowerCase().includes(q)),
  );
  const pick = useCallback((name: string | null, push = true) => {
    setError("");
    if (push) window.history.pushState(null, "", name ? `/explore?city=${encodeURIComponent(name)}` : "/explore");
    if (!name) {
      setCity(null);
      return;
    }
    getCity(name)
      .then((c) => {
        setCity(c);
        setTab("restaurant");
        setInfo("intro");
        window.scrollTo({ top: 0, behavior: "smooth" });
      })
      .catch((e) => setError((e as Error).message));
  }, []);
  useEffect(() => {
    getCities()
      .then(setCities)
      .catch((e) => setError((e as Error).message));
    const fromUrl = () => pick(new URLSearchParams(window.location.search).get("city"), false);
    fromUrl();
    window.addEventListener("popstate", fromUrl);
    return () => window.removeEventListener("popstate", fromUrl);
  }, [pick]);
  return (
    <div className="page">
      <TopBar user={user} />
      <main className="column explore">
        {error && (
          <p className="error" role="alert">
            {error.charAt(0).toUpperCase() + error.slice(1)}
          </p>
        )}
        {!city && (
          <>
            <header className="explore-head">
              <h1>Explore</h1>
              <p className="muted">
                {cities.length} destinations across India and Nepal: restaurants, sights, cafes and photo spots, with
                the travel basics for each place.
              </p>
            </header>
            <div className="explore-tools">
              <label className="search">
                <span className="sr-only">Search destinations</span>
                <input
                  type="search"
                  value={query}
                  placeholder="Search a city, for example Manali"
                  onChange={(e) => setQuery(e.target.value)}
                  onKeyDown={(e) => {
                    const exact = cities.find((c) => c.name.toLowerCase() === query.trim().toLowerCase());
                    if (e.key === "Enter" && query.trim()) pick(exact ? exact.name : query.trim());
                  }}
                />
              </label>
              <div className="chips filter-chips" role="group" aria-label="Kind of trip">
                {FILTERS.map(([id, label]) => (
                  <button
                    key={id}
                    type="button"
                    className="chip"
                    aria-pressed={filter === id}
                    onClick={() => setFilter(id)}
                  >
                    {label}
                  </button>
                ))}
              </div>
            </div>
            <div className="city-grid">
              {shown.length === 0 && (
                <p className="muted">
                  No destination matches. Press Enter to look it up anyway, it works when Google Maps is connected.
                </p>
              )}
              {shown.map((c) => (
                <button key={c.name} type="button" className="city-card" onClick={() => pick(c.name)}>
                  <Photo id={c.photo_id ?? c.name} kind="city" name={c.name} src={c.photo_url} />
                  <span className="city-text">
                    <strong>{c.name}</strong>
                    <span className="city-tagline">{c.tagline}</span>
                    <span className="city-counts">
                      {c.counts.attraction} sights · {c.counts.restaurant} restaurants · {c.counts.cafe} cafes
                    </span>
                  </span>
                </button>
              ))}
            </div>
          </>
        )}
        {city && (
          <article className="city">
            <button type="button" className="link small" onClick={() => pick(null)}>
              All destinations
            </button>
            <header className="city-hero">
              <Photo id={city.name} kind="city" name={city.name} src={city.photo_url} eager />
              <div className="city-hero-text">
                <h1>{city.name}</h1>
                <p>{city.tagline}</p>
              </div>
            </header>
            <nav className="tabs explore-tabs" role="tablist" aria-label="Categories">
              {TABS.map(([id, label]) => (
                <button key={id} type="button" role="tab" aria-selected={tab === id} onClick={() => setTab(id)}>
                  {label} <span className="count">{city.sections[id].length}</span>
                </button>
              ))}
            </nav>
            <div className="tile-grid" key={tab}>
              {city.sections[tab].map((c) => (
                <CardTile key={`${tab}-${c.id}`} card={c} onOpen={setOpen} />
              ))}
            </div>
            {city.sections[tab].length === 0 && (
              <p className="muted">
                The travel guide does not list any {TABS.find((x) => x[0] === tab)![1].toLowerCase()} for {city.name}{" "}
                yet. Try another category, or search on{" "}
                <a
                  href={`https://www.google.com/maps/search/${encodeURIComponent(`${tab}s in ${city.name}`)}`}
                  target="_blank"
                  rel="noreferrer"
                >
                  Google Maps
                </a>
                .
              </p>
            )}
            <section>
              <h2>Top places in {city.name}</h2>
              <ol className="top-strip">
                {city.top.map((c, i) => (
                  <li key={c.id}>
                    <button type="button" className="top-card" onClick={() => setOpen(c)}>
                      <Photo id={c.id} kind={c.category} name={c.name} src={c.photo_url} />
                      <span className="rank">{i + 1}</span>
                      <strong>{c.name}</strong>
                    </button>
                  </li>
                ))}
              </ol>
            </section>
            <section className="travel-info">
              <h2>Travel information</h2>
              <nav className="tabs info-tabs" role="tablist" aria-label="Travel information">
                {Object.keys(INFO_NAMES)
                  .filter((id) => city.info[id])
                  .map((id) => (
                    <button key={id} type="button" role="tab" aria-selected={info === id} onClick={() => setInfo(id)}>
                      {INFO_NAMES[id]}
                    </button>
                  ))}
              </nav>
              <p className="info-text" key={info}>
                {city.info[info] ?? "No travel information for this place yet."}
              </p>
            </section>
            <p className="muted small source-line">
              Places from {city.places_from}.{" "}
              {city.source && (
                <>
                  Travel information from{" "}
                  <a href={city.source} target="_blank" rel="noreferrer">
                    Wikivoyage
                  </a>
                  , shared under CC BY-SA 4.0.
                </>
              )}
            </p>
          </article>
        )}
      </main>
      {open && <PlaceSheet card={open} onClose={close} />}
    </div>
  );
}

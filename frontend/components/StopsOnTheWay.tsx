"use client";
// places worth a stop between the start and the destination
import type { Card, RouteStops } from "@/lib/api";
import Photo from "./Photo";
import { KIND_NAMES } from "./PlaceSheet";

export default function StopsOnTheWay({
  route,
  onOpen,
  byRoad,
}: {
  route: RouteStops;
  onOpen: (c: Card) => void;
  byRoad: boolean;
}) {
  return (
    <section className="stops">
      <h3>Stops on the way</h3>
      <p className="muted small">
        {route.origin} to {route.destination}, {route.road}.{" "}
        {byRoad
          ? "Good places to break the journey."
          : "Handy if you drive or go by bus, or for a slower trip another time."}
      </p>
      <ol className="stop-line">
        {route.stops.map((s) => (
          <li key={s.id}>
            <button type="button" className="stop-card" onClick={() => onOpen(s)}>
              <Photo id={s.id} kind={s.kind} name={s.name} />
              <span className="stop-text">
                <span className="kicker">
                  {KIND_NAMES[s.kind] ?? "Town"} ·{" "}
                  {s.on_way ? "on the way" : `${s.detour_km ? `about ${s.detour_km} km` : "short"} detour`}
                </span>
                <strong>{s.name}</strong>
                <span className="muted small">
                  About {s.from_start_km} km from {route.origin} · {s.time}
                </span>
                {s.eat && <span className="small">Eat: {s.eat.name}</span>}
              </span>
            </button>
          </li>
        ))}
      </ol>
      {route.source && <p className="muted small">{route.source}.</p>}
    </section>
  );
}

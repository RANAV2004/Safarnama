"use client";
// details of one place: photo, description, tips and where it is
import { useEffect, useRef, useState } from "react";
import type { Card, Media } from "@/lib/api";
import { rupees } from "@/lib/format";
import MapView from "./MapView";
import Photo, { loadMedia } from "./Photo";

export const KIND_NAMES: Record<string, string> = {
  attraction: "Attraction",
  restaurant: "Restaurant",
  cafe: "Cafe",
  photo: "Photo spot",
  nature: "Nature",
  history: "History",
  beach: "Beach",
  food: "Food stop",
  culture: "Culture",
  shopping: "Shopping",
  town: "Town",
  science: "Science",
};

export default function PlaceSheet({ card, onClose }: { card: Card; onClose: () => void }) {
  const [media, setMedia] = useState<Media | null>(null);
  const closeBtn = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    loadMedia(card.id).then(setMedia);
    closeBtn.current?.focus();
    const esc = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    document.addEventListener("keydown", esc);
    document.body.classList.add("no-scroll");
    return () => {
      document.removeEventListener("keydown", esc);
      document.body.classList.remove("no-scroll");
    };
  }, [card.id, onClose]);
  const kind = card.kind === "attraction" ? card.category : card.kind;
  return (
    <div className="overlay sheet-overlay" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div className="sheet" role="dialog" aria-modal="true" aria-label={card.name}>
        <div className="sheet-photo">
          <Photo id={card.id} kind={kind} name={card.name} eager />
          <button ref={closeBtn} type="button" className="sheet-close" onClick={onClose} aria-label="Close">
            <svg
              viewBox="0 0 24 24"
              width="20"
              height="20"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              aria-hidden="true"
            >
              <path d="M6 6l12 12M18 6 6 18" />
            </svg>
          </button>
        </div>
        <div className="sheet-body">
          <p className="kicker">
            {KIND_NAMES[card.kind] ?? card.kind}
            {card.area ? ` · ${card.area}` : ""}
            {card.price ? ` · ${card.price}` : ""}
          </p>
          <h2>{card.name}</h2>
          {card.rating ? (
            <p className="rating">
              <span aria-hidden="true">★</span> {card.rating}
              {card.reviews ? (
                <span className="muted small"> from {card.reviews.toLocaleString("en-IN")} reviews on Google</span>
              ) : null}
            </p>
          ) : null}
          <p>{card.text || media?.extract}</p>
          {card.must_try && (
            <p>
              <strong>Must try:</strong> {card.must_try}
            </p>
          )}
          {card.tip && <p className="tip">{card.tip}</p>}
          {"eat" in card && (card as { eat?: { name: string; text: string } }).eat && (
            <p className="tip">
              <strong>Where to eat:</strong> {(card as { eat: { name: string; text: string } }).eat.name}.{" "}
              {(card as { eat: { name: string; text: string } }).eat.text}
            </p>
          )}
          {card.hours && (
            <p className="small">
              <strong>Open:</strong> {card.hours}
            </p>
          )}
          {card.entry_fee_inr !== undefined && card.kind === "attraction" && (
            <p className="muted small">
              {card.entry_fee_inr ? `Entry ${rupees(card.entry_fee_inr)} a person` : "Free entry"}
            </p>
          )}
          <h3>Where it is</h3>
          {card.lat !== null && card.lng !== null ? (
            <MapView lat={card.lat} lng={card.lng} name={card.name} />
          ) : (
            <p className="muted small">The exact spot is not on our map yet. Google Maps finds it by name.</p>
          )}
          <div className="sheet-actions">
            <a className="btn-primary" href={card.maps_url} target="_blank" rel="noreferrer">
              Open in Google Maps
            </a>
            <a
              className="btn-secondary"
              href={
                card.lat !== null && card.lng !== null
                  ? `https://www.google.com/maps/dir/?api=1&destination=${card.lat},${card.lng}`
                  : card.maps_url.replace("/search/?api=1&query=", "/dir/?api=1&destination=")
              }
              target="_blank"
              rel="noreferrer"
            >
              Directions
            </a>
          </div>
          <p className="muted small">
            {card.source === "Google Maps" ? (
              <>Details from Google Maps{card.photo_by ? `, photo by ${card.photo_by} on Google` : ""}.</>
            ) : card.source?.startsWith("https://en.wikivoyage.org/") ? (
              <>
                Description from{" "}
                <a href={card.source} target="_blank" rel="noreferrer">
                  Wikivoyage
                </a>{" "}
                (CC BY-SA).
              </>
            ) : null}
            {media?.page && (
              <>
                {" "}
                Photo from{" "}
                <a href={media.page} target="_blank" rel="noreferrer">
                  {media.page.includes("commons.wikimedia.org") ? "Wikimedia Commons" : "Wikipedia"}
                </a>
                , open it to see who took it and its licence.
              </>
            )}
          </p>
        </div>
      </div>
    </div>
  );
}

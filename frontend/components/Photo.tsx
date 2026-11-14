"use client";
// photo of a place from Wikipedia, with drawn artwork when there is no photo
import { useEffect, useRef, useState } from "react";
import { getMedia, type Media } from "@/lib/api";

const cache = new Map<string, Promise<Media | null>>();
const ICONS: Record<string, string> = {
  restaurant: "M7 3v8M5 3v4a2 2 0 0 0 4 0V3M7 11v10M17 3c-2 0-3 2-3 5s1 4 3 4v9",
  cafe: "M4 9h13v4a5 5 0 0 1-5 5H9a5 5 0 0 1-5-5V9M17 10h1a2 2 0 0 1 0 4h-1M8 3c0 2 1 2 1 4M12 3c0 2 1 2 1 4",
  photo: "M4 8h3l2-3h6l2 3h3v11H4V8M12 17a4 4 0 1 0 0-8 4 4 0 0 0 0 8",
  food: "M3 12h18a9 6 0 0 1-18 0M8 9c0-2 1-2 1-4M12 9c0-2 1-2 1-4M16 9c0-2 1-2 1-4",
  beach: "M3 17c2 0 2-1.5 4.5-1.5S10 17 12 17s2-1.5 4.5-1.5S19 17 21 17M17 4a3 3 0 1 1 0 6 3 3 0 0 1 0-6",
  nature: "M5 19c0-8 6-13 15-14-1 9-6 15-14 15M5 19l7-7",
  history: "M4 21V9h3V6h2v3h2V6h2v3h2V6h2v3h3v12H4M10 21v-5h4v5",
  culture: "M12 3 3 8h18l-9-5M5 8v10M9 8v10M15 8v10M19 8v10M3 21h18",
  shopping: "M5 8h14l-1 13H6L5 8M9 8V6a3 3 0 0 1 6 0v2",
  city: "M3 21V10l5-3v14M8 21V5l6-3v19M14 21V9l7 3v9M3 21h18",
};
const TINTS: Record<string, [string, string]> = {
  restaurant: ["#ffe0cc", "#f6a07a"],
  cafe: ["#f4e4d4", "#c89f7c"],
  food: ["#ffe0cc", "#f6a07a"],
  photo: ["#e4e0ff", "#9c8cf0"],
  beach: ["#d9f3f7", "#6cc4d6"],
  nature: ["#dff3e2", "#79c08a"],
  history: ["#fbe9d0", "#d9a35f"],
  culture: ["#fde7ef", "#f48fb1"],
  shopping: ["#fde7ef", "#f48fb1"],
};

export function loadMedia(id: string): Promise<Media | null> {
  if (!cache.has(id))
    cache.set(
      id,
      getMedia(id).catch(() => null),
    );
  return cache.get(id)!;
}

export function Artwork({ kind, label }: { kind: string; label: string }) {
  const [from, to] = TINTS[kind] ?? ["#fde7ef", "#f48fb1"];
  return (
    <div
      className="artwork"
      style={{ background: `linear-gradient(135deg, ${from}, ${to})` }}
      role="img"
      aria-label={label}
    >
      <svg
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.4"
        strokeLinecap="round"
        strokeLinejoin="round"
        aria-hidden="true"
      >
        <path d={ICONS[kind] ?? ICONS.city} />
      </svg>
    </div>
  );
}

export default function Photo({
  id,
  kind,
  name,
  src,
  eager = false,
}: {
  id: string;
  kind: string;
  name: string;
  src?: string | null;
  eager?: boolean;
  cover?: boolean;
}) {
  const box = useRef<HTMLDivElement>(null);
  const [media, setMedia] = useState<Media | null | undefined>(
    src ? { title: name, extract: "", image: src, page: "" } : undefined,
  );
  const [loaded, setLoaded] = useState(false);
  useEffect(() => {
    if (src) {
      setMedia({ title: name, extract: "", image: src, page: "" });
      return;
    }
    let alive = true;
    const start = () => loadMedia(id).then((m) => alive && setMedia(m));
    if (eager || typeof IntersectionObserver === "undefined") {
      start();
      return () => {
        alive = false;
      };
    }
    const seen = new IntersectionObserver(
      (entries) => {
        if (entries.some((e) => e.isIntersecting)) {
          seen.disconnect();
          start();
        }
      },
      { rootMargin: "300px" },
    );
    if (box.current) seen.observe(box.current);
    return () => {
      alive = false;
      seen.disconnect();
    };
  }, [id, eager, src, name]);
  return (
    <div ref={box} className="photo">
      {media?.image ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img
          src={media.image}
          alt={name}
          loading={eager ? "eager" : "lazy"}
          decoding="async"
          fetchPriority={eager ? "high" : "auto"}
          className={loaded ? "shown" : ""}
          onLoad={() => setLoaded(true)}
          onError={() => setMedia(null)}
        />
      ) : null}
      {!(media?.image && loaded) && <Artwork kind={kind} label={media === undefined ? `Loading ${name}` : name} />}
    </div>
  );
}

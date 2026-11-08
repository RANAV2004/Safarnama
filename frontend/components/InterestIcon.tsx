// interest icon
const PATHS: Record<string, string> = {
  beaches:
    "M3 17c2 0 2-1.5 4.5-1.5S10 17 12 17s2-1.5 4.5-1.5S19 17 21 17M3 21c2 0 2-1.5 4.5-1.5S10 21 12 21s2-1.5 4.5-1.5S19 21 21 21M17 4a3 3 0 1 1 0 6 3 3 0 0 1 0-6",
  mountains: "M2 20 9 7l4 7 2-3 7 9H2M9 7l2 4",
  trekking: "M5 20c2-3 4-3 6-6s2-6 5-8M16 6V2l4 2-4 2M4 20h4",
  views: "M3 18h18M6 18a6 6 0 0 1 12 0M12 7V4M5.6 9.6 3.5 7.5M18.4 9.6l2.1-2.1",
  history: "M4 21V9h3V6h2v3h2V6h2v3h2V6h2v3h3v12H4M10 21v-5h4v5",
  nature: "M5 19c0-8 6-13 15-14-1 9-6 15-14 15M5 19l7-7",
  shopping: "M5 8h14l-1 13H6L5 8M9 8V6a3 3 0 0 1 6 0v2",
  food: "M3 12h18a9 6 0 0 1-18 0M8 9c0-2 1-2 1-4M12 9c0-2 1-2 1-4M16 9c0-2 1-2 1-4",
  spiritual: "M12 2v3M8 10a4 4 0 0 1 8 0M6 10h12v3H6zM7 13v8h10v-8M11 21v-4h2v4",
  culture:
    "M12 3a9 9 0 1 0 0 18c1.5 0 2-1 1.5-2s0-2 1.5-2H18a3 3 0 0 0 3-3c0-6-4-11-9-11M7.5 10.5h.01M10.5 7h.01M15 7.5h.01",
  adventure: "M13 2 4 14h7l-1 8 9-12h-7l1-8",
  clubs: "M5 3h14l-7 9-7-9M12 12v8M8 21h8M3 15c1.5 0 1.5-1 3-1M17 7h4M19 5v4",
  nightlife: "M20 14A8 8 0 1 1 10 4a6 6 0 0 0 10 10M17 3v4M15 5h4",
  quiet: "M4 10h13v4a5 5 0 0 1-5 5H9a5 5 0 0 1-5-5v-4M17 11h1a2 2 0 0 1 0 4h-1M8 3c0 2 1 2 1 4M12 3c0 2 1 2 1 4",
  family: "M8 7a2.5 2.5 0 1 0 0-.01M16 8a2 2 0 1 0 0-.01M3 21v-3a5 5 0 0 1 10 0v3M13 21v-2a3.5 3.5 0 0 1 7 0v2",
};

export default function InterestIcon({ id }: { id: string }) {
  return (
    <svg
      viewBox="0 0 24 24"
      width="30"
      height="30"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.6"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d={PATHS[id] ?? "M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18"} />
    </svg>
  );
}

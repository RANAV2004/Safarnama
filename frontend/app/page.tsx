"use client";
// splash page
import { useRouter } from "next/navigation";
import { useEffect } from "react";
import { getSession } from "@/lib/auth";
const ROUTE = "M30 96 C 150 14, 260 120, 380 54 S 540 26, 590 70";

export default function Splash() {
  const router = useRouter();
  useEffect(() => {
    const next = getSession() ? "/dashboard" : "/login";
    const quiet = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const timer = setTimeout(() => router.replace(next), quiet ? 1400 : 3600);
    const skip = () => router.replace(next);
    window.addEventListener("keydown", skip);
    return () => {
      clearTimeout(timer);
      window.removeEventListener("keydown", skip);
    };
  }, [router]);
  return (
    <main className="splash" onClick={() => router.replace(getSession() ? "/dashboard" : "/login")}>
      <svg className="splash-route" viewBox="0 0 620 130" aria-hidden="true">
        <defs>
          <mask id="reveal">
            <path className="splash-draw" d={ROUTE} pathLength={1} />
          </mask>
        </defs>
        <path className="splash-dots" d={ROUTE} mask="url(#reveal)" />
        <circle className="splash-pin start" cx="30" cy="96" r="7" />
        <circle className="splash-pin end" cx="590" cy="70" r="7" />
      </svg>
      <h1 className="splash-word" aria-label="Safarnama">
        {"Safarnama".split("").map((ch, i) => (
          <span key={i} aria-hidden="true" style={{ animationDelay: `${0.9 + i * 0.07}s` }}>
            {ch}
          </span>
        ))}
      </h1>
      <p className="splash-hindi" lang="hi">
        सफ़रनामा
      </p>
      <p className="splash-tag">The story of your next journey</p>
      <button className="splash-skip" type="button">
        Skip
      </button>
    </main>
  );
}

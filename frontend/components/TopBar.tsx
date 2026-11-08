"use client";
// top bar
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { logOut } from "@/lib/api";
import { clearSession, type User } from "@/lib/auth";

export default function TopBar({ user }: { user: User | null }) {
  const router = useRouter();
  const path = usePathname() ?? "";
  const [open, setOpen] = useState(false);
  const box = useRef<HTMLDivElement>(null);
  useEffect(() => {
    function close(e: MouseEvent | KeyboardEvent) {
      if (e instanceof KeyboardEvent ? e.key === "Escape" : !box.current?.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", close);
    document.addEventListener("keydown", close);
    return () => {
      document.removeEventListener("mousedown", close);
      document.removeEventListener("keydown", close);
    };
  }, []);
  async function signOut() {
    clearSession();
    await logOut().catch(() => {});
    router.replace("/login");
  }
  const first = user?.name.split(" ")[0] ?? "";
  return (
    <header className="topbar">
      <Link href="/dashboard" className="brand">
        Safarnama <span lang="hi">सफ़रनामा</span>
      </Link>
      {user && (
        <nav className="main-nav" aria-label="Main">
          <Link href="/dashboard" aria-current={path.startsWith("/dashboard") ? "page" : undefined}>
            Plan
          </Link>
          <Link href="/explore" aria-current={path.startsWith("/explore") ? "page" : undefined}>
            Explore
          </Link>
        </nav>
      )}
      {user && (
        <div className="who" ref={box}>
          <button type="button" className="hi" aria-haspopup="menu" aria-expanded={open} onClick={() => setOpen(!open)}>
            <span className="avatar" aria-hidden="true">
              {first.charAt(0).toUpperCase()}
            </span>
            Hi, {first}
            <svg
              viewBox="0 0 24 24"
              width="16"
              height="16"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              aria-hidden="true"
            >
              <path d="m6 9 6 6 6-6" />
            </svg>
          </button>
          {open && (
            <div className="menu" role="menu">
              <p className="menu-head">
                <strong>{user.name}</strong>
                <span className="muted small">{user.email}</span>
                <span className="muted small">User ID #{user.id}</span>
              </p>
              <Link role="menuitem" href="/dashboard" onClick={() => setOpen(false)}>
                Plan a trip
              </Link>
              <Link role="menuitem" href="/settings" onClick={() => setOpen(false)}>
                Settings
              </Link>
              <Link role="menuitem" href="/settings#trips" onClick={() => setOpen(false)}>
                My itineraries
              </Link>
              <Link role="menuitem" href="/welcome" onClick={() => setOpen(false)}>
                Interests
              </Link>
              <Link role="menuitem" href="/settings#help" onClick={() => setOpen(false)}>
                Help center
              </Link>
              {user.role === "admin" && (
                <Link role="menuitem" href="/admin" onClick={() => setOpen(false)}>
                  Admin panel
                </Link>
              )}
              <button type="button" role="menuitem" onClick={signOut}>
                Sign out
              </button>
            </div>
          )}
        </div>
      )}
    </header>
  );
}

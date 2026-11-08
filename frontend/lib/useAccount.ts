"use client";
// signed in account for a page, sends you to sign in when the session has ended
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { AuthError, logOut, whoAmI } from "./api";
import { clearSession, getSession, saveSession, type User } from "./auth";

export function useAccount() {
  const router = useRouter();
  const [user, setUser] = useState<User | null>(null);
  useEffect(() => {
    const s = getSession();
    if (!s) {
      router.replace("/login");
      return;
    }
    setUser(s.user);
    whoAmI()
      .then((u) => {
        setUser(u);
        saveSession({ user: u });
      })
      .catch((e) => {
        if (e instanceof AuthError) {
          clearSession();
          router.replace("/login?expired=1");
        }
      });
  }, [router]);
  const expired = useCallback(() => {
    clearSession();
    logOut().catch(() => {});
    router.replace("/login?expired=1");
  }, [router]);
  return { user, setUser, expired };
}

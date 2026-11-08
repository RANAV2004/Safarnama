"use client";
// registers the service worker so the site can be installed as an app
import { useEffect } from "react";

export default function InstallApp() {
  useEffect(() => {
    if ("serviceWorker" in navigator && process.env.NODE_ENV === "production") {
      navigator.serviceWorker.register("/sw.js").catch(() => {});
    }
  }, []);
  return null;
}

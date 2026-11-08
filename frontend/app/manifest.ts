// web app manifest, lets phones install Safarnama like an app
import type { MetadataRoute } from "next";

export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "Safarnama trip planner",
    short_name: "Safarnama",
    description: "Plan trips across India with a team of AI agents, explore places and travel with friends.",
    start_url: "/dashboard",
    scope: "/",
    display: "standalone",
    orientation: "portrait",
    background_color: "#fff6f9",
    theme_color: "#c2185b",
    categories: ["travel"],
    icons: [
      { src: "/icons/icon-192.png", sizes: "192x192", type: "image/png" },
      { src: "/icons/icon-512.png", sizes: "512x512", type: "image/png" },
      { src: "/icons/maskable-512.png", sizes: "512x512", type: "image/png", purpose: "maskable" },
    ],
    shortcuts: [
      { name: "Plan a trip", url: "/dashboard" },
      { name: "Explore", url: "/explore" },
    ],
  };
}

// copy world map
import { copyFileSync, statSync } from "node:fs";
const from = new URL("../node_modules/world-atlas/countries-110m.json", import.meta.url);
const to = new URL("../public/world-110m.json", import.meta.url);
copyFileSync(from, to);
console.log(`public/world-110m.json, ${(statSync(to).size / 1024).toFixed(0)} KB`);

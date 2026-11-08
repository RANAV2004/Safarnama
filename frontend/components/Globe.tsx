"use client";
// globe
import {
  geoDistance,
  geoGraticule10,
  geoInterpolate,
  geoOrthographic,
  geoPath,
  type GeoPermissibleObjects,
} from "d3-geo";
import { useEffect, useImperativeHandle, useRef, type Ref } from "react";
import { feature, mesh } from "topojson-client";
import type { Topology } from "topojson-specification";
import type { Place } from "@/lib/places";
export type GlobeHandle = {
  travel: (from: Place, to: Place) => Promise<void>;
  finish: () => Promise<void>;
  reset: () => void;
  skip: () => void;
};
const PINK = "194, 24, 91";
const IDLE_SPIN = 7;
const IDLE_ALPHA = 0.38;
const SIZE = 0.62;
const ARC_PX = 230;
const FOLLOW = 7;
const MAX_DPR = 2;
const graticule = geoGraticule10();
type Tween = { start: number; dur: number; step: (k: number) => void; done: () => void };

const ease = (k: number) => (k < 0.5 ? 4 * k * k * k : 1 - Math.pow(-2 * k + 2, 3) / 2);

const lerp = (a: number, b: number, k: number) => a + (b - a) * k;

const turnTo = (from: number, to: number) => from + ((((to - from) % 360) + 540) % 360) - 180;

export default function Globe({ ref }: { ref?: Ref<GlobeHandle> }) {
  const canvas = useRef<HTMLCanvasElement>(null);
  const world = useRef<{ land: GeoPermissibleObjects; borders: GeoPermissibleObjects } | null>(null);
  const view = useRef({ lon: -78, lat: -18, zoom: 1, alpha: IDLE_ALPHA, idle: true });
  const goal = useRef({ lon: -78, lat: -18, zoom: 1, alpha: IDLE_ALPHA, idle: true });
  const trip = useRef<{ from?: Place; to?: Place; progress: number; pins: Place[]; pingAt: number }>({
    progress: 0,
    pins: [],
    pingAt: 0,
  });
  const tweens = useRef<Tween[]>([]);
  const speed = useRef(1);
  const quiet = useRef(false);
  function tween(dur: number, step: (k: number) => void) {
    return new Promise<void>((done) =>
      tweens.current.push({ start: performance.now(), dur: quiet.current ? 1 : dur, step, done }),
    );
  }
  useImperativeHandle(ref, () => ({
    async travel(from, to) {
      speed.current = 1;
      tweens.current = [];
      const v = goal.current,
        t = trip.current;
      v.idle = false;
      Object.assign(t, { from, to, progress: 0, pins: [] });
      const radius =
        (canvas.current?.clientWidth ? Math.min(canvas.current.clientWidth, canvas.current.clientHeight) : 600) * SIZE;
      const target = Math.min(
        16,
        Math.max(2.5, ARC_PX / (radius * Math.max(geoDistance([from.lon, from.lat], [to.lon, to.lat]), 0.001))),
      );
      const s = { lon: v.lon, lat: v.lat, zoom: v.zoom, alpha: v.alpha };
      const endLon = turnTo(s.lon, -from.lon);
      await tween(1200, (k) => {
        const e = ease(k);
        v.lon = lerp(s.lon, endLon, e);
        v.lat = lerp(s.lat, -from.lat, e);
        v.zoom = lerp(s.zoom, target, e);
        v.alpha = lerp(s.alpha, 0.95, e);
      });
      t.pins = [from];
      t.pingAt = performance.now();
      await tween(250, () => {});
      const along = geoInterpolate([from.lon, from.lat], [to.lon, to.lat]);
      await tween(2000, (k) => {
        const e = ease(k);
        t.progress = e;
        const [lon, lat] = along(e);
        v.lon = turnTo(v.lon, -lon);
        v.lat = -lat;
      });
      t.pins = [from, to];
      t.pingAt = performance.now();
      await tween(800, () => {});
    },
    async finish() {
      const v = goal.current;
      const s = { lon: v.lon, zoom: v.zoom, alpha: v.alpha };
      await tween(1300, (k) => {
        const e = ease(k);
        v.lon = s.lon + 160 * e;
        v.zoom = s.zoom * Math.pow(0.05 / s.zoom, e);
        v.alpha = lerp(s.alpha, 0, Math.max(0, (e - 0.35) / 0.65));
      });
    },
    reset() {
      speed.current = 1;
      tweens.current = [];
      const v = goal.current;
      Object.assign(trip.current, { from: undefined, to: undefined, progress: 0, pins: [] });
      const s = { lat: v.lat };
      v.idle = true;
      v.zoom = 0.6;
      tween(1000, (k) => {
        const e = ease(k);
        v.zoom = lerp(0.6, 1, e);
        v.alpha = lerp(0, IDLE_ALPHA, e);
        v.lat = lerp(s.lat, -18, e);
      });
    },
    skip() {
      speed.current = 5;
    },
  }));
  useEffect(() => {
    quiet.current = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    fetch("/world-110m.json")
      .then((r) => r.json())
      .then((topo: Topology) => {
        const countries = topo.objects.countries as Parameters<typeof mesh>[1];
        world.current = {
          land: feature(topo, topo.objects.land) as GeoPermissibleObjects,
          borders: mesh(topo, countries, (a, b) => a !== b),
        };
      })
      .catch(() => {});
    const el = canvas.current!;
    const ctx = el.getContext("2d")!;
    const projection = geoOrthographic().clipAngle(90).precision(0.6);
    const path = geoPath(projection, ctx);
    let last = performance.now();
    let frame = 0;
    function fit() {
      const dpr = Math.min(MAX_DPR, window.devicePixelRatio || 1);
      el.width = el.clientWidth * dpr;
      el.height = el.clientHeight * dpr;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    }
    function stroke(obj: GeoPermissibleObjects, alpha: number, width: number, dash: number[] = [], offset = 0) {
      ctx.beginPath();
      path(obj);
      ctx.setLineDash(dash);
      ctx.lineDashOffset = offset;
      ctx.strokeStyle = `rgba(${PINK}, ${alpha})`;
      ctx.lineWidth = width;
      ctx.stroke();
    }
    function dot(p: Place, now: number, label: boolean, ping = true) {
      const v = view.current;
      if (geoDistance([p.lon, p.lat], [-v.lon, -v.lat]) > Math.PI / 2) return;
      const [x, y] = projection([p.lon, p.lat])!;
      const age = (now - trip.current.pingAt) / 900;
      if (ping && age >= 0 && age < 1) {
        ctx.beginPath();
        ctx.arc(x, y, 6 + age * 26, 0, Math.PI * 2);
        ctx.strokeStyle = `rgba(${PINK}, ${0.8 * (1 - age) * v.alpha})`;
        ctx.lineWidth = 2;
        ctx.setLineDash([]);
        ctx.stroke();
      }
      ctx.beginPath();
      ctx.arc(x, y, 6, 0, Math.PI * 2);
      ctx.fillStyle = `rgba(${PINK}, ${v.alpha})`;
      ctx.fill();
      if (label) {
        ctx.font = "600 16px Mukta, system-ui, sans-serif";
        ctx.fillStyle = `rgba(${PINK}, ${v.alpha})`;
        ctx.fillText(p.name, x + 12, y - 10);
      }
    }
    function draw(now: number) {
      const dt = Math.min(0.05, (now - last) / 1000);
      last = now;
      const v = view.current,
        t = trip.current;
      for (const tw of [...tweens.current]) {
        if (speed.current > 1) tw.start -= (speed.current - 1) * dt * 1000;
        const k = Math.min(1, (now - tw.start) / tw.dur);
        tw.step(k);
        if (k >= 1) {
          tweens.current = tweens.current.filter((x) => x !== tw);
          tw.done();
        }
      }
      const g = goal.current;
      if (g.idle && !quiet.current) g.lon += IDLE_SPIN * dt;
      const f = quiet.current ? 1 : 1 - Math.exp(-dt * FOLLOW);
      v.lon += (turnTo(v.lon, g.lon) - v.lon) * f;
      v.lat += (g.lat - v.lat) * f;
      v.zoom *= Math.pow(g.zoom / v.zoom, f);
      v.alpha += (g.alpha - v.alpha) * f;
      v.idle = g.idle;
      const w = el.clientWidth,
        h = el.clientHeight;
      ctx.clearRect(0, 0, w, h);
      projection
        .translate([w / 2, h / 2])
        .scale(Math.min(w, h) * SIZE * v.zoom)
        .rotate([v.lon, v.lat, 0]);
      const a = v.alpha;
      if (a > 0.005) {
        stroke({ type: "Sphere" }, a * 0.9, 1.6);
        stroke(graticule, a * 0.28, 0.7);
        if (world.current) {
          stroke(world.current.land, a, 1.3);
          stroke(world.current.borders, a * 0.5, 0.7);
        }
        if (t.from && t.to && t.progress > 0) {
          const here = geoInterpolate([t.from.lon, t.from.lat], [t.to.lon, t.to.lat])(t.progress);
          stroke({ type: "LineString", coordinates: [[t.from.lon, t.from.lat], here] }, a, 3, [2, 8], -now / 40);
          dot({ name: "", lon: here[0], lat: here[1] }, now, false, false);
        }
        for (const p of t.pins) dot(p, now, true);
      }
      frame = requestAnimationFrame(draw);
    }
    fit();
    window.addEventListener("resize", fit);
    frame = requestAnimationFrame(draw);
    return () => {
      cancelAnimationFrame(frame);
      window.removeEventListener("resize", fit);
    };
  }, []);
  return <canvas ref={canvas} className="globe" aria-hidden="true" />;
}

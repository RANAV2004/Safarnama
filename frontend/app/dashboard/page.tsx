"use client";
// dashboard page
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import Globe, { type GlobeHandle } from "@/components/Globe";
import ChatPanel from "@/components/ChatPanel";
import Friends from "@/components/Friends";
import Itinerary from "@/components/Itinerary";
import TripForm from "@/components/TripForm";
import TopBar from "@/components/TopBar";
import {
  API_URL,
  AuthError,
  NO_PINS,
  downloadPdf,
  getProfile,
  getRoutes,
  getTrip,
  isDirty,
  streamPlan,
  type AgentEvent,
  type Pins,
  type Plan,
  type Route,
  type TripRequest,
} from "@/lib/api";
import { getSession } from "@/lib/auth";
import { useAccount } from "@/lib/useAccount";
import { AGENT_NAMES, addDays, isoDay, shortDate, toRupeeSign } from "@/lib/format";
import { place } from "@/lib/places";
const start = addDays(isoDay(new Date()), 14);
const DEFAULT: TripRequest = {
  origin: "Indore",
  destination: "Goa",
  start_date: start,
  end_date: addDays(start, 3),
  budget_inr: 15000,
  travellers: 2,
  preferences: [],
  note: "",
};
const SUCK_MS = 900;
const TO_FORM: Record<string, string> = {
  beaches: "beach",
  history: "history",
  nature: "nature",
  shopping: "shopping",
  culture: "culture",
  spiritual: "culture",
};
type Phase = "form" | "flying" | "result";

function suckInto(el: HTMLElement) {
  const r = el.getBoundingClientRect();
  el.style.transformOrigin = `${window.innerWidth / 2 - r.left}px ${window.innerHeight / 2 - r.top}px`;
  el.style.transition = `transform ${SUCK_MS}ms cubic-bezier(.5, 0, .75, 0), opacity ${SUCK_MS * 0.8}ms cubic-bezier(.5, 0, .75, 0)`;
  el.style.transform = "rotate(6deg) scale(0.06)";
  el.style.opacity = "0";
}

function restore(el: HTMLElement, pop: boolean) {
  el.style.transition = "none";
  el.style.transform = "";
  el.style.opacity = "";
  el.classList.remove("pop-in");
  if (pop) {
    void el.offsetWidth;
    el.classList.add("pop-in");
  }
}

export default function Dashboard() {
  const router = useRouter();
  const { user, expired } = useAccount();
  const [routes, setRoutes] = useState<Route[]>([]);
  const [trip, setTrip] = useState<TripRequest>(DEFAULT);
  const [pins, setPins] = useState<Pins>(NO_PINS);
  const [plan, setPlan] = useState<Plan | null>(null);
  const [phase, setPhase] = useState<Phase>("form");
  const [showForm, setShowForm] = useState(true);
  const [caption, setCaption] = useState("");
  const [error, setError] = useState("");
  const [downloading, setDownloading] = useState(false);
  const [interests, setInterests] = useState<string[]>([]);
  const stage = useRef<HTMLDivElement>(null);
  const globe = useRef<GlobeHandle>(null);
  useEffect(() => {
    const s = getSession();
    if (!s) return;
    const open = Number(new URLSearchParams(window.location.search).get("trip"));
    if (open) {
      getTrip(open)
        .then((t) => {
          showPlan(t.plan);
          setShowForm(false);
          setPhase("result");
        })
        .catch((e) =>
          setError(e instanceof AuthError ? "Sign in again to open this itinerary." : (e as Error).message),
        );
      window.history.replaceState(null, "", "/dashboard");
    }
    getProfile()
      .then((p) => {
        if (!p.onboarded && !open) {
          router.replace("/welcome");
          return;
        }
        setInterests(p.options.filter((o) => p.interests.includes(o.id)).map((o) => o.label));
        setTrip((t) =>
          t.preferences.length
            ? t
            : { ...t, preferences: [...new Set(p.interests.map((i) => TO_FORM[i]).filter(Boolean))] },
        );
      })
      .catch(() => {});
    getRoutes()
      .then(setRoutes)
      .catch(() =>
        setError(`Can't reach the planner at ${API_URL}. Start the backend with: uvicorn app.api:app --reload`),
      );
  }, []);
  function changeTrip(next: TripRequest) {
    if (next.origin !== trip.origin || next.destination !== trip.destination) setPins(NO_PINS);
    else if (next.start_date !== trip.start_date || next.end_date !== trip.end_date)
      setPins((p) => ({ ...p, outbound_id: undefined, return_id: undefined, my_outbound: null, my_return: null }));
    setTrip(next);
  }
  async function generate() {
    const before = phase;
    const el = stage.current!;
    setError("");
    setCaption("Your agents are starting");
    window.scrollTo({ top: 0, behavior: "smooth" });
    suckInto(el);
    setPhase("flying");
    let final: Plan | null = null;
    let failed = "";
    const same =
      plan &&
      plan.request.origin === trip.origin &&
      plan.request.destination === trip.destination &&
      plan.request.start_date === trip.start_date &&
      plan.request.end_date === trip.end_date;
    const planning = streamPlan(
      { ...trip, ...pins },
      (e: AgentEvent) => {
        if (e.agent === "done" && e.plan) final = e.plan;
        else if (e.agent === "error") {
          failed = e.note ?? "Planning failed.";
          globe.current?.skip();
        } else if (AGENT_NAMES[e.agent]) setCaption(`${AGENT_NAMES[e.agent]}: ${toRupeeSign(e.note ?? "")}`);
      },
      same ? plan?.trip_id : undefined,
    ).catch((err) => {
      globe.current?.skip();
      if (err instanceof AuthError) failed = "auth";
      else
        failed =
          err instanceof TypeError
            ? `Can't reach the planner at ${API_URL}. Is the backend running?`
            : (err as Error).message;
    });
    await Promise.all([globe.current?.travel(place(trip.origin), place(trip.destination)), planning]);
    if (failed || !final) {
      if (failed === "auth") return expired();
      globe.current?.reset();
      restore(el, true);
      setPhase(before);
      setError(failed || "Planning failed.");
      return;
    }
    setCaption("Your itinerary is ready");
    await globe.current?.finish();
    showPlan(final as Plan);
    setShowForm(false);
    setPhase("result");
    restore(el, true);
    globe.current?.reset();
  }
  function showPlan(p: Plan) {
    const r = p.request;
    setPlan(p);
    setTrip({
      origin: r.origin,
      destination: r.destination,
      start_date: r.start_date,
      end_date: r.end_date,
      budget_inr: r.budget_inr,
      travellers: r.travellers,
      preferences: r.preferences,
      note: r.note ?? "",
    });
    setPins({
      outbound_id: r.outbound_id ?? undefined,
      return_id: r.return_id ?? undefined,
      stay_id: r.stay_id ?? undefined,
      include_places: r.include_places ?? [],
      exclude_places: r.exclude_places ?? [],
      my_outbound: r.my_outbound ?? null,
      my_return: r.my_return ?? null,
    });
  }
  async function download() {
    if (!plan) return;
    setDownloading(true);
    try {
      const url = URL.createObjectURL(await downloadPdf(plan));
      const a = document.createElement("a");
      a.href = url;
      a.download = `safarnama-${plan.request.origin}-${plan.request.destination}-${plan.request.start_date}.pdf`
        .toLowerCase()
        .replace(/[^a-z0-9.-]+/g, "-");
      document.body.appendChild(a);
      a.click();
      a.remove();
      setTimeout(() => URL.revokeObjectURL(url), 10000);
    } catch (err) {
      if (err instanceof AuthError) return expired();
      setError((err as Error).message);
    } finally {
      setDownloading(false);
    }
  }
  const flying = phase === "flying";
  return (
    <div className="dash">
      <Globe ref={globe} />
      <TopBar user={user} />
      <main className="column">
        {error && (
          <p className="error" role="alert">
            {toRupeeSign(error)}
          </p>
        )}
        {interests.length > 0 && !plan && phase === "form" && (
          <p className="interest-line">
            Planning around what you love: {interests.join(", ")}.{" "}
            <button type="button" className="link small" onClick={() => router.push("/welcome")}>
              Change
            </button>
          </p>
        )}
        <div ref={stage} className="stage" aria-hidden={flying} style={flying ? { pointerEvents: "none" } : undefined}>
          {plan && !showForm && (
            <div className="edit-row">
              <button
                type="button"
                className="btn-ghost"
                onClick={() => {
                  setPlan(null);
                  setPins(NO_PINS);
                  setShowForm(true);
                }}
              >
                Plan a new trip
              </button>
              <button type="button" className="btn-ghost" onClick={() => setShowForm(true)}>
                Edit trip details
              </button>
            </div>
          )}
          {routes.length > 0 && (showForm || !plan) ? (
            <TripForm
              routes={routes}
              value={trip}
              onChange={changeTrip}
              onSubmit={generate}
              busy={flying}
              hasPlan={!!plan}
            />
          ) : (
            routes.length === 0 && !error && <p className="muted center">Loading</p>
          )}
          {plan && (
            <Itinerary
              plan={plan}
              pins={pins}
              setPins={setPins}
              dirty={isDirty(plan, trip, pins)}
              busy={flying}
              downloading={downloading}
              onRegenerate={generate}
              onDownload={download}
            />
          )}
          {plan?.trip_id && (
            <Friends
              key={plan.trip_id}
              tripId={plan.trip_id}
              route={`${plan.request.origin} to ${plan.request.destination}`}
              dates={`${shortDate(plan.request.start_date)} to ${shortDate(plan.request.end_date)}`}
              user={user}
              onAuthError={expired}
              onLeft={() => {
                setPlan(null);
                setPins(NO_PINS);
                setShowForm(true);
              }}
            />
          )}
          {plan && (
            <ChatPanel
              key={`${plan.request.destination}-${plan.request.start_date}`}
              plan={plan}
              onPlan={showPlan}
              onAuthError={() => expired()}
            />
          )}
        </div>
      </main>
      {flying && (
        <div className="flight-caption" role="status" aria-live="polite">
          <p className="flight-route">
            {trip.origin} to {trip.destination}
          </p>
          <p className="flight-step">{caption}</p>
          <button type="button" className="link small" onClick={() => globe.current?.skip()}>
            Skip animation
          </button>
        </div>
      )}
    </div>
  );
}

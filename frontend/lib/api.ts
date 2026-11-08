// api calls
import type { Session, User } from "./auth";
export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
export type MyJourney = {
  mode: "flight" | "train" | "bus";
  provider: string;
  number: string;
  depart_at: string;
  arrive_at: string;
  price_inr: number;
};
export type Booking = MyJourney & { from_city: string | null; to_city: string | null };
export type Pins = {
  outbound_id?: string;
  return_id?: string;
  stay_id?: string;
  include_places: string[];
  exclude_places: string[];
  my_outbound?: MyJourney | null;
  my_return?: MyJourney | null;
};
export const NO_PINS: Pins = { include_places: [], exclude_places: [] };
export type TripRequest = {
  origin: string;
  destination: string;
  start_date: string;
  end_date: string;
  budget_inr: number;
  travellers: number;
  preferences: string[];
  note: string;
} & Partial<Pins>;
export type Route = { from: string; to: string };
export type Transport = {
  id: string;
  mode: "flight" | "train" | "bus";
  provider: string;
  depart_at: string;
  arrive_at: string;
  price_inr: number;
  overnight: boolean;
};
export type Stay = {
  id: string;
  name: string;
  area: string;
  price_per_night_inr: number;
  rating: number | null;
  late_checkin: boolean;
  checkin_until: string;
};
export type Place = {
  id: string;
  name: string;
  category: string;
  entry_fee_inr: number;
  est_hours: number;
  closed_days: string[];
};
export type PlanItem = {
  start: string;
  end: string;
  title: string;
  kind: "travel" | "checkin" | "place" | "free";
  place_id: string | null;
  cost_inr: number;
};
export type DayPlan = { date: string; weekday: string; items: PlanItem[]; km: number };
export type TraceEvent = { agent: string; note: string };
export type Plan = {
  trip_id?: number;
  request: TripRequest;
  summary: string;
  outbound: Transport | null;
  return: Transport | null;
  stay: Stay | null;
  places: Place[];
  days: DayPlan[];
  breakdown: Record<string, number>;
  total_cost: number;
  over_budget_by: number;
  negotiation_rounds: number;
  notes: string[];
  trace: TraceEvent[];
  options: { outbound: Transport[]; return: Transport[]; stays: Stay[]; places: Place[] };
  details?: Record<string, Card>;
  meals?: Meal[];
  stops?: RouteStops | null;
};
export type CardKind =
  | "attraction"
  | "restaurant"
  | "cafe"
  | "photo"
  | "nature"
  | "history"
  | "beach"
  | "food"
  | "culture";
export type Card = {
  id: string;
  name: string;
  kind: CardKind;
  category: string;
  area?: string;
  text: string;
  tip?: string;
  lat: number | null;
  lng: number | null;
  wiki?: string;
  image?: string;
  price?: string;
  hours?: string;
  must_try?: string;
  rating?: number | null;
  reviews?: number;
  photo_by?: string;
  entry_fee_inr?: number;
  maps_url: string;
  source?: string;
};
export type Stop = Card & {
  on_way: boolean;
  time: string;
  from_start_km: number;
  progress: number;
  detour_km?: number;
  eat?: { name: string; text: string };
};
export type RouteStops = { origin: string; destination: string; road: string; stops: Stop[]; source?: string };
export type Meal = { date: string; picks: (Card & { km: number })[] };
export type Media = { title: string; extract: string; image: string | null; page: string; credit?: string };
export type CitySummary = {
  name: string;
  tagline: string;
  tags: string[];
  lat: number | null;
  lng: number | null;
  banner: string | null;
  photo_id?: string | null;
  counts: Record<string, number>;
};
export type CityGuide = CitySummary & {
  info: Record<string, string>;
  top: Card[];
  sections: Record<"attraction" | "restaurant" | "cafe" | "photo", Card[]>;
  labels: Record<string, string>;
  source: string;
  places_from: "Google Maps" | "Wikivoyage";
  licence: string;
};
export type Member = { id: number; name: string; role: "owner" | "member" };
export type Invite = { token: string; expires: number; days: number };
export type InvitePreview = {
  trip_id: number;
  origin: string;
  destination: string;
  start_date: string;
  end_date: string;
  invited_by: string;
  members: string[];
  joined: boolean;
};
export type AgentEvent = { agent: string; note?: string; plan?: Plan };
export type Learned = { likes: string[]; avoids: string[]; interests?: string[] };
export type Understood = {
  text: string;
  masked: string;
  intent: string;
  label: string;
  confidence: number;
  done: boolean;
};
export type Interest = { id: string; label: string; hint: string };
export type Profile = { email: string; interests: string[]; onboarded: boolean; options: Interest[] };
export type ModelInfo = {
  seed: number;
  learned: number;
  by_source: Record<string, number>;
  intents: Record<string, string>;
};
export type Source = { title: string; text: string };
export type Revision = {
  reply: string;
  changes: string[];
  answer: string;
  sources: Source[];
  plan: Plan | null;
  learned: Learned;
  understood: Understood[];
  turn_id: number;
};
export type Memory = Learned & { items: { city: string; text: string; created: string }[] };
export class AuthError extends Error {}

function readError(body: unknown): string {
  const detail = (body as { detail?: unknown })?.detail;
  if (typeof detail === "string") return detail.charAt(0).toUpperCase() + detail.slice(1);
  if (Array.isArray(detail)) return detail.map((d) => String(d.msg ?? d).replace(/^Value error, /, "")).join(". ");
  return "Something went wrong. Try again.";
}

async function call(path: string, opts: { body?: unknown; method?: string } = {}): Promise<Response> {
  const headers: Record<string, string> = { "x-requested-with": "safarnama" };
  if (opts.body !== undefined) headers["content-type"] = "application/json";
  const res = await fetch(`${API_URL}${path}`, {
    method: opts.method ?? (opts.body !== undefined ? "POST" : "GET"),
    headers,
    credentials: "include",
    body: opts.body !== undefined ? JSON.stringify(opts.body) : undefined,
  });
  if (res.status === 401) throw new AuthError(readError(await res.json().catch(() => null)));
  if (!res.ok) throw new Error(readError(await res.json().catch(() => null)));
  return res;
}

export const getRoutes = async (): Promise<Route[]> => (await call("/routes")).json();

export const signUp = async (body: {
  name: string;
  email: string;
  birth_date: string;
  password: string;
}): Promise<Session> => (await call("/auth/signup", { body })).json();

export const logIn = async (email: string, password: string): Promise<Session> =>
  (await call("/auth/login", { body: { email, password } })).json();

export const startReset = async (email: string): Promise<void> => {
  await call("/auth/forgot/start", { body: { email } });
};

export const forgotPassword = async (email: string, code: string, new_password: string): Promise<Session> =>
  (await call("/auth/forgot", { body: { email, code, new_password } })).json();

export const logOut = async (): Promise<void> => {
  await call("/auth/logout", { body: {} });
};

export const changePassword = async (current_password: string, new_password: string): Promise<Session> =>
  (await call("/auth/change-password", { body: { current_password, new_password } })).json();

export const whoAmI = async (): Promise<User> => (await call("/auth/me")).json();
export type TripSummary = {
  id: number;
  user_id: number;
  origin: string;
  destination: string;
  start_date: string;
  end_date: string;
  travellers: number;
  budget_inr: number;
  total_cost: number;
  created: string;
  updated: string;
  user_name?: string;
  user_email?: string;
  owner_name?: string;
  shared?: boolean;
};
export type AdminUser = User & { trips: number };
export type AdminUserDetail = AdminUser & { itineraries: TripSummary[] };

export const myTrips = async (): Promise<TripSummary[]> => (await call("/trips")).json();

export const getTrip = async (id: number): Promise<TripSummary & { plan: Plan; members: Member[] }> =>
  (await call(`/trips/${id}`)).json();

export const inviteFriends = async (tripId: number): Promise<Invite> =>
  (await call(`/trips/${tripId}/invite`, { body: {} })).json();

export const removeMember = async (tripId: number, userId: number): Promise<void> => {
  await call(`/trips/${tripId}/members/${userId}`, { method: "DELETE" });
};

export const getInvite = async (token: string): Promise<InvitePreview> =>
  (await call(`/invites/${encodeURIComponent(token)}`)).json();

export const acceptInvite = async (token: string): Promise<{ trip_id: number }> =>
  (await call(`/invites/${encodeURIComponent(token)}/accept`, { body: {} })).json();

export const getCities = async (): Promise<CitySummary[]> => (await call("/explore")).json();

export const getCity = async (name: string): Promise<CityGuide> =>
  (await call(`/explore/${encodeURIComponent(name)}`)).json();

export const getMedia = async (id: string): Promise<Media> => (await call(`/media/${encodeURIComponent(id)}`)).json();

export const readBooking = async (text: string, mode: MyJourney["mode"]): Promise<Booking> =>
  (await call("/bookings/parse", { body: { text, mode } })).json();

export const deleteTrip = async (id: number): Promise<void> => {
  await call(`/trips/${id}`, { method: "DELETE" });
};

export const adminStats = async (): Promise<{ users: number; banned: number; itineraries: number }> =>
  (await call("/admin/stats")).json();

export const adminUsers = async (q: string): Promise<AdminUser[]> =>
  (await call(`/admin/users?q=${encodeURIComponent(q)}`)).json();

export const adminUser = async (id: number): Promise<AdminUserDetail> => (await call(`/admin/users/${id}`)).json();

export const adminBan = async (id: number, banned: boolean): Promise<AdminUserDetail> =>
  (await call(`/admin/users/${id}/ban`, { body: { banned } })).json();

export const adminDelete = async (id: number): Promise<void> => {
  await call(`/admin/users/${id}`, { method: "DELETE" });
};

export const adminTrips = async (q: string): Promise<TripSummary[]> =>
  (await call(`/admin/trips?q=${encodeURIComponent(q)}`)).json();

export const downloadPdf = async (plan: Plan): Promise<Blob> => (await call("/plan/pdf", { body: plan })).blob();

export const revisePlan = async (plan: Plan, message: string): Promise<Revision> =>
  (await call("/plan/revise", { body: { plan, message, trip_id: plan.trip_id ?? null } })).json();

export const teach = async (
  turn_id: number,
  good: boolean,
  fixes: Record<number, string> = {},
): Promise<{ learned: number; model: ModelInfo }> => (await call("/learn", { body: { turn_id, good, fixes } })).json();

export const getModel = async (): Promise<ModelInfo> => (await call("/model")).json();

export const getProfile = async (): Promise<Profile> => (await call("/profile")).json();

export const saveProfile = async (interests: string[]): Promise<Profile> =>
  (await call("/profile", { body: { interests }, method: "PUT" })).json();

export const getMemory = async (): Promise<Memory> => (await call("/memory")).json();

export const forgetMemory = async (): Promise<{ forgot: number }> =>
  (await call("/memory", { method: "DELETE" })).json();

export async function streamPlan(req: TripRequest, onEvent: (e: AgentEvent) => void, tripId?: number): Promise<void> {
  const res = await call(`/plan/stream${tripId ? `?trip_id=${tripId}` : ""}`, { body: req });
  const reader = res.body!.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const chunks = buffer.split("\n\n");
    buffer = chunks.pop() ?? "";
    for (const chunk of chunks) {
      const line = chunk.split("\n").find((l) => l.startsWith("data: "));
      if (line) onEvent(JSON.parse(line.slice(6)));
    }
  }
}

export function isDirty(plan: Plan, trip: TripRequest, pins: Pins): boolean {
  const r = plan.request;
  const same = (a?: string | null, b?: string | null) => (a ?? null) === (b ?? null);
  const sameList = (a: string[] = [], b: string[] = []) => a.length === b.length && a.every((x) => b.includes(x));
  const fields =
    r.origin === trip.origin &&
    r.destination === trip.destination &&
    r.start_date === trip.start_date &&
    r.end_date === trip.end_date &&
    r.budget_inr === trip.budget_inr &&
    r.travellers === trip.travellers &&
    sameList(r.preferences, trip.preferences) &&
    (r.note ?? "") === trip.note;
  const choices =
    same(r.outbound_id, pins.outbound_id) &&
    same(r.return_id, pins.return_id) &&
    same(r.stay_id, pins.stay_id) &&
    sameList(r.include_places, pins.include_places) &&
    sameList(r.exclude_places, pins.exclude_places) &&
    sameJourney(r.my_outbound, pins.my_outbound) &&
    sameJourney(r.my_return, pins.my_return);
  return !(fields && choices);
}

function sameJourney(a?: MyJourney | null, b?: MyJourney | null): boolean {
  if (!a || !b) return !a && !b;
  return (
    a.depart_at.slice(0, 16) === b.depart_at.slice(0, 16) &&
    a.arrive_at.slice(0, 16) === b.arrive_at.slice(0, 16) &&
    a.mode === b.mode &&
    a.provider === b.provider &&
    a.number === b.number &&
    a.price_inr === b.price_inr
  );
}

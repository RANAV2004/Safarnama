// format helpers
export const rupees = (n: number) => `₹${n.toLocaleString("en-IN")}`;

export const toRupeeSign = (text: string) => text.replace(/Rs (?=\d)/g, "₹");
export const AGENT_NAMES: Record<string, string> = {
  coordinator: "Coordinator",
  transport: "Transport agent",
  stay: "Stay agent",
  places: "Places agent",
  budget_check: "Budget check",
  writer: "Itinerary writer",
  critic: "Critic",
};

export function shortDate(iso: string) {
  return new Date(`${iso.slice(0, 10)}T00:00:00`).toLocaleDateString("en-IN", {
    weekday: "short",
    day: "numeric",
    month: "short",
  });
}

export function clock(iso: string) {
  return iso.slice(11, 16);
}

export function isoDay(d: Date) {
  const local = new Date(d.getTime() - d.getTimezoneOffset() * 60000);
  return local.toISOString().slice(0, 10);
}

export function addDays(iso: string, n: number) {
  const d = new Date(`${iso}T00:00:00`);
  d.setDate(d.getDate() + n);
  return isoDay(d);
}

export function nightsBetween(start: string, end: string) {
  return Math.round((new Date(`${end}T00:00:00`).getTime() - new Date(`${start}T00:00:00`).getTime()) / 86400000);
}

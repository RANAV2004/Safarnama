// signed in user, the session token itself lives in an httpOnly cookie
const KEY = "safarnama.user";
export type User = {
  id: number;
  name: string;
  email: string;
  birth_date: string;
  role: "user" | "admin";
  banned: boolean;
  created: string;
  last_login: string | null;
};
export type Session = { user: User };

export function getSession(): Session | null {
  try {
    const raw = localStorage.getItem(KEY);
    const user = raw ? (JSON.parse(raw) as User) : null;
    return user && user.id ? { user } : null;
  } catch {
    return null;
  }
}

export function saveSession(s: Session) {
  try {
    localStorage.setItem(KEY, JSON.stringify(s.user));
  } catch {}
}

export function clearSession() {
  try {
    localStorage.removeItem(KEY);
    localStorage.removeItem("safarnama.session");
  } catch {}
}

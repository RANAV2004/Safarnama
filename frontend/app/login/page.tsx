"use client";
// login page
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { API_URL, AuthError, forgotPassword, getProfile, logIn, signUp, startReset, whoAmI } from "@/lib/api";
import { clearSession, getSession, saveSession, type Session } from "@/lib/auth";
import { isoDay } from "@/lib/format";
type Mode = "login" | "signup" | "forgot";

function nextPage(): string | null {
  const next = new URLSearchParams(window.location.search).get("next") ?? "";
  return /^\/(join|explore|dashboard)(\/[A-Za-z0-9_-]*)?$/.test(next) ? next : null;
}
const TITLES: Record<Mode, string> = {
  login: "Welcome back",
  signup: "Create your account",
  forgot: "Reset your password",
};

function Password({
  label,
  value,
  onChange,
  autoComplete,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  autoComplete: string;
}) {
  const [show, setShow] = useState(false);
  return (
    <label>
      <span className="label">{label}</span>
      <span className="password">
        <input
          type={show ? "text" : "password"}
          autoComplete={autoComplete}
          required
          value={value}
          onChange={(e) => onChange(e.target.value)}
        />
        <button
          type="button"
          className="link small"
          onClick={() => setShow(!show)}
          aria-label={show ? "Hide password" : "Show password"}
        >
          {show ? "Hide" : "Show"}
        </button>
      </span>
    </label>
  );
}

export default function Login() {
  const router = useRouter();
  const [mode, setMode] = useState<Mode>("login");
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [birth, setBirth] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [info, setInfo] = useState("");
  const [busy, setBusy] = useState(false);
  const [code, setCode] = useState("");
  const [codeSent, setCodeSent] = useState(false);
  useEffect(() => {
    if (new URLSearchParams(window.location.search).get("expired"))
      setInfo("Your session ended. Sign in again to keep planning.");
    if (nextPage()?.startsWith("/join")) setInfo("Sign in or create an account to join your friend's trip.");
    const s = getSession();
    if (s)
      whoAmI()
        .then(() => router.replace(nextPage() ?? "/dashboard"))
        .catch((e) => e instanceof AuthError && clearSession());
  }, [router]);
  function switchMode(m: Mode) {
    setMode(m);
    setError("");
    setInfo("");
    setPassword("");
    setCode("");
    setCodeSent(false);
  }
  async function done(s: Session) {
    saveSession(s);
    const me = await getProfile().catch(() => null);
    router.replace(nextPage() ?? (me && !me.onboarded ? "/welcome" : "/dashboard"));
  }
  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      if (mode === "login") await done(await logIn(email, password));
      else if (mode === "signup") await done(await signUp({ name, email, birth_date: birth, password }));
      else if (!codeSent) {
        await startReset(email);
        setCodeSent(true);
        setInfo("If an account uses this email, we sent it a 6 digit code. It works for 15 minutes.");
        setBusy(false);
      } else await done(await forgotPassword(email, code, password));
    } catch (err) {
      setError(
        err instanceof TypeError
          ? `Can't reach the server at ${API_URL}. Start the backend with: uvicorn app.api:app --reload`
          : (err as Error).message,
      );
      setBusy(false);
    }
  }
  const today = isoDay(new Date());
  return (
    <main className="auth">
      <div className="auth-backdrop" aria-hidden="true">
        <svg className="auth-route" viewBox="0 0 620 130">
          <path className="auth-route-line" d="M30 96 C 150 14, 260 120, 380 54 S 540 26, 590 70" pathLength={1} />
          <circle className="auth-pin" cx="30" cy="96" r="7" />
          <circle className="auth-pin end" cx="590" cy="70" r="7" />
        </svg>
        <p className="auth-word">
          {"Safarnama".split("").map((ch, i) => (
            <span key={i} style={{ animationDelay: `${i * 45}ms` }}>
              {ch}
            </span>
          ))}
        </p>
        <p className="auth-hindi" lang="hi">
          सफ़रनामा
        </p>
        <p className="auth-tag">The story of your next journey</p>
      </div>
      <div className="auth-card">
        <p className="brand">
          Safarnama <span lang="hi">सफ़रनामा</span>
        </p>
        {mode !== "forgot" && (
          <div className="tabs" role="tablist">
            <button type="button" role="tab" aria-selected={mode === "login"} onClick={() => switchMode("login")}>
              Sign in
            </button>
            <button type="button" role="tab" aria-selected={mode === "signup"} onClick={() => switchMode("signup")}>
              Create account
            </button>
          </div>
        )}
        <form onSubmit={submit} className="stack">
          <h1>{TITLES[mode]}</h1>
          {mode === "forgot" && (
            <p className="muted">
              {codeSent
                ? "Enter the code from your email and choose a new password."
                : "Enter your email and we will send you a code to choose a new password."}
            </p>
          )}
          {info && <p className="notice">{info}</p>}
          {mode === "signup" && (
            <label>
              <span className="label">Full name</span>
              <input
                autoComplete="name"
                required
                maxLength={60}
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="Vansh Rana"
              />
            </label>
          )}
          <label>
            <span className="label">Email</span>
            <input
              type="email"
              autoComplete="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="you@example.com"
            />
          </label>
          {mode === "forgot" && codeSent && (
            <label>
              <span className="label">Code from your email</span>
              <input
                inputMode="numeric"
                autoComplete="one-time-code"
                required
                pattern="[0-9]{6}"
                maxLength={6}
                value={code}
                onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))}
              />
            </label>
          )}
          {mode === "signup" && (
            <label>
              <span className="label">Date of birth</span>
              <input
                type="date"
                autoComplete="bday"
                required
                max={today}
                min="1900-01-01"
                value={birth}
                onChange={(e) => setBirth(e.target.value)}
              />
            </label>
          )}
          {(mode !== "forgot" || codeSent) && (
            <Password
              label={mode === "login" ? "Password" : "New password"}
              value={password}
              onChange={setPassword}
              autoComplete={mode === "login" ? "current-password" : "new-password"}
            />
          )}
          {(mode === "signup" || codeSent) && (
            <p className="hint">At least 8 characters, with a letter and a number.</p>
          )}
          {mode === "login" && (
            <button type="button" className="link small forgot" onClick={() => switchMode("forgot")}>
              Forgot password?
            </button>
          )}
          {error && (
            <p className="error" role="alert">
              {error}
            </p>
          )}
          <button className="btn-primary" disabled={busy}>
            {busy
              ? "Please wait"
              : mode === "login"
                ? "Sign in"
                : mode === "signup"
                  ? "Create account"
                  : codeSent
                    ? "Reset password and sign in"
                    : "Send me a code"}
          </button>
          {mode === "forgot" && (
            <button type="button" className="link" onClick={() => switchMode("login")}>
              Back to sign in
            </button>
          )}
        </form>
      </div>
    </main>
  );
}

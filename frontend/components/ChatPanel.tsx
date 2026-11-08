"use client";
// chat panel
import { useEffect, useRef, useState } from "react";
import {
  AuthError,
  forgetMemory,
  getMemory,
  getModel,
  revisePlan,
  teach,
  type Learned,
  type ModelInfo,
  type Plan,
  type Source,
  type Understood,
} from "@/lib/api";
import { toRupeeSign } from "@/lib/format";
type Feedback = "none" | "good" | "fixing" | "taught";
type Message = {
  from: "you" | "safarnama";
  text: string;
  changes?: string[];
  sources?: Source[];
  turn?: number;
  understood?: Understood[];
  ask?: string;
  before?: Plan;
  feedback?: Feedback;
};
type Props = { plan: Plan; onPlan: (p: Plan) => void; onAuthError: () => void };
const NAMES: Record<string, string> = {
  beach: "beaches",
  history: "history",
  shopping: "shopping",
  nature: "nature",
  culture: "culture",
  science: "science",
};

function suggestions(plan: Plan): string[] {
  const out = ["Add another beach", "Get me a cheaper hotel"];
  const other = plan.options.outbound.find((t) => t.mode !== plan.outbound?.mode);
  if (other) out.push(`Go by ${other.mode}`);
  if (plan.places[0]) out.push(`What is ${plan.places[0].name}?`);
  return out;
}

function Thumb({ down }: { down?: boolean }) {
  return (
    <svg
      viewBox="0 0 24 24"
      width="16"
      height="16"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      style={down ? { transform: "rotate(180deg)" } : undefined}
    >
      <path d="M7 10v11H4V10h3zm0 0 4-8a3 3 0 0 1 3 3v4h5a2 2 0 0 1 2 2.3l-1.3 7.5A2 2 0 0 1 17.7 21H7" />
    </svg>
  );
}

function Fixer({
  msg,
  intents,
  busy,
  onTeach,
}: {
  msg: Message;
  intents: Record<string, string>;
  busy: boolean;
  onTeach: (fixes: Record<number, string>) => void;
}) {
  const [picks, setPicks] = useState<string[]>((msg.understood ?? []).map((u) => u.intent));
  return (
    <form
      className="fixer"
      onSubmit={(e) => {
        e.preventDefault();
        onTeach(Object.fromEntries(picks.map((p, i) => [i, p])));
      }}
    >
      <p className="small">
        <strong>What did you mean?</strong> Fix any part and I will learn it.
      </p>
      {(msg.understood ?? []).map((u, i) => (
        <label key={i} className="fix-row">
          <span>"{u.text}"</span>
          <select value={picks[i]} onChange={(e) => setPicks(picks.map((p, j) => (j === i ? e.target.value : p)))}>
            {Object.entries(intents).map(([id, label]) => (
              <option key={id} value={id}>
                {label}
              </option>
            ))}
          </select>
        </label>
      ))}
      <button type="submit" className="btn-secondary small-btn" disabled={busy}>
        Teach me and try again
      </button>
    </form>
  );
}

export default function ChatPanel({ plan, onPlan, onAuthError }: Props) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [learned, setLearned] = useState<Learned>({ likes: [], avoids: [] });
  const [count, setCount] = useState(0);
  const [model, setModel] = useState<ModelInfo | null>(null);
  const end = useRef<HTMLDivElement>(null);
  function refresh() {
    getMemory()
      .then((m) => {
        setLearned(m);
        setCount(m.items.length);
      })
      .catch(() => {});
    getModel()
      .then(setModel)
      .catch(() => {});
  }
  useEffect(refresh, []);
  useEffect(() => {
    end.current?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }, [messages.length]);
  function update(i: number, patch: Partial<Message>) {
    setMessages((old) => old.map((m, j) => (j === i ? { ...m, ...patch } : m)));
  }
  async function send(message: string, base: Plan = plan, retry = false) {
    const m = message.trim();
    if (!m || busy) return;
    if (!retry) setMessages((old) => [...old, { from: "you", text: m }]);
    setText("");
    setBusy(true);
    try {
      const r = await revisePlan(base, m);
      setMessages((old) => [
        ...old,
        {
          from: "safarnama",
          text: r.answer && r.reply !== r.answer && !r.reply.startsWith(r.answer) ? `${r.answer} ${r.reply}` : r.reply,
          changes: r.changes,
          sources: r.sources,
          turn: r.turn_id,
          understood: r.understood,
          ask: m,
          before: base,
          feedback: retry ? "taught" : "none",
        },
      ]);
      setLearned(r.learned);
      if (r.plan) onPlan(r.plan);
      refresh();
    } catch (err) {
      if (err instanceof AuthError) return onAuthError();
      setMessages((old) => [...old, { from: "safarnama", text: (err as Error).message }]);
    } finally {
      setBusy(false);
    }
  }
  async function thumbsUp(i: number, msg: Message) {
    update(i, { feedback: "good" });
    try {
      await teach(msg.turn!, true);
      refresh();
    } catch (err) {
      if (err instanceof AuthError) onAuthError();
    }
  }
  async function fix(i: number, msg: Message, fixes: Record<number, string>) {
    setBusy(true);
    try {
      await teach(msg.turn!, false, fixes);
      update(i, { feedback: "taught" });
      if (msg.before) onPlan(msg.before);
      setBusy(false);
      await send(msg.ask!, msg.before ?? plan, true);
    } catch (err) {
      setBusy(false);
      if (err instanceof AuthError) onAuthError();
    }
  }
  async function forget() {
    try {
      await forgetMemory();
      setLearned({ likes: [], avoids: [] });
      setCount(0);
    } catch (err) {
      if (err instanceof AuthError) onAuthError();
    }
  }
  const remembers = learned.likes.length > 0 || learned.avoids.length > 0 || count > 0;
  return (
    <section className="card chat" aria-label="Change your plan">
      <div>
        <h3>Change anything, or ask</h3>
        <p className="muted small">
          Tell Safarnama what to add, remove or swap, in your own words. Its own model reads your message, and it learns
          every time you tell it whether it got you right.
        </p>
      </div>
      {messages.length > 0 && (
        <ol className="messages" aria-live="polite">
          {messages.map((msg, i) => (
            <li key={i} className={`msg ${msg.from}`}>
              <p>{toRupeeSign(msg.text)}</p>
              {msg.changes && msg.changes.length > 0 && (
                <ul className="changes">
                  {msg.changes.map((c, j) => (
                    <li key={j}>{toRupeeSign(c)}</li>
                  ))}
                </ul>
              )}
              {msg.sources && msg.sources.length > 0 && (
                <p className="sources">From the travel guide: {msg.sources.map((s) => s.title).join(", ")}</p>
              )}
              {msg.understood && msg.understood.length > 0 && (
                <p className="sources">I understood: {msg.understood.map((u) => u.label).join(", ")}</p>
              )}
              {msg.turn && msg.feedback === "none" && (
                <div className="rate">
                  <span className="small muted">Did I get that right?</span>
                  <button type="button" className="rate-btn" disabled={busy} onClick={() => thumbsUp(i, msg)}>
                    <Thumb /> Yes
                  </button>
                  <button
                    type="button"
                    className="rate-btn"
                    disabled={busy}
                    onClick={() => update(i, { feedback: "fixing" })}
                  >
                    <Thumb down /> Not right
                  </button>
                </div>
              )}
              {msg.feedback === "good" && <p className="sources">Thanks, I learned from this.</p>}
              {msg.feedback === "taught" && i === messages.length - 1 && (
                <p className="sources">Learned from your correction.</p>
              )}
              {msg.feedback === "fixing" && model && (
                <Fixer msg={msg} intents={model.intents} busy={busy} onTeach={(f) => fix(i, msg, f)} />
              )}
            </li>
          ))}
          {busy && (
            <li className="msg safarnama typing" aria-label="Safarnama is replanning">
              <span />
              <span />
              <span />
            </li>
          )}
        </ol>
      )}
      <div ref={end} />
      <div className="chips">
        {suggestions(plan).map((s) => (
          <button key={s} type="button" className="chip" disabled={busy} onClick={() => send(s)}>
            {s}
          </button>
        ))}
      </div>
      <form
        className="ask"
        onSubmit={(e) => {
          e.preventDefault();
          send(text);
        }}
      >
        <label className="sr-only" htmlFor="ask">
          Your message
        </label>
        <textarea
          id="ask"
          rows={2}
          maxLength={500}
          value={text}
          placeholder="For example: remove the flea market, I want more beaches and a cheaper hotel"
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              send(text);
            }
          }}
        />
        <button type="submit" className="btn-primary" disabled={busy || !text.trim()}>
          {busy ? "Replanning" : "Send"}
        </button>
      </form>
      <div className="memory">
        <p>
          {remembers && (
            <>
              <strong>Safarnama remembers</strong>{" "}
            </>
          )}
          {learned.likes.length > 0 && <span>you like {learned.likes.map((c) => NAMES[c] ?? c).join(", ")}. </span>}
          {learned.avoids.length > 0 && <span>you skip {learned.avoids.map((c) => NAMES[c] ?? c).join(", ")}. </span>}
          {count > 0 && (
            <span className="muted">
              {count} change{count > 1 ? "s" : ""} saved.{" "}
            </span>
          )}
          {model && (
            <span className="muted">
              Model trained on {model.seed + model.learned} examples, {model.learned} learned from travellers.
            </span>
          )}
        </p>
        {remembers && (
          <button type="button" className="link small" onClick={forget}>
            Forget
          </button>
        )}
      </div>
    </section>
  );
}

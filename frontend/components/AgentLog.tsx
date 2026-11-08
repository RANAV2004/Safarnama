// agent log
import type { AgentEvent } from "@/lib/api";
import { AGENT_NAMES, toRupeeSign } from "@/lib/format";
type Props = { events: AgentEvent[]; running?: boolean };

export default function AgentLog({ events, running = false }: Props) {
  const steps = events.filter((e) => AGENT_NAMES[e.agent]);
  return (
    <ol className="journey" aria-live="polite">
      {steps.map((e, i) => {
        const again = steps.slice(0, i).some((s) => s.agent === e.agent) && e.agent !== "budget_check";
        return (
          <li key={i} className={`stop ${again ? "again" : ""}`}>
            <span className="stop-name">
              {AGENT_NAMES[e.agent]}
              {again && <em> again</em>}
            </span>
            <span className="stop-note">{toRupeeSign(e.note ?? "")}</span>
          </li>
        );
      })}
      {running && (
        <li className="stop pending">
          <span className="stop-name">Working</span>
        </li>
      )}
    </ol>
  );
}

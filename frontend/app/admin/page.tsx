"use client";
// admin page
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import TopBar from "@/components/TopBar";
import TripViewer from "@/components/TripViewer";
import {
  AuthError,
  adminBan,
  adminDelete,
  adminStats,
  adminTrips,
  adminUser,
  adminUsers,
  type AdminUser,
  type AdminUserDetail,
  type TripSummary,
} from "@/lib/api";
import { rupees, shortDate } from "@/lib/format";
import { useAccount } from "@/lib/useAccount";
type Tab = "users" | "trips";

export default function Admin() {
  const router = useRouter();
  const { user, expired } = useAccount();
  const [tab, setTab] = useState<Tab>("users");
  const [q, setQ] = useState("");
  const [stats, setStats] = useState<{ users: number; banned: number; itineraries: number } | null>(null);
  const [users, setUsers] = useState<AdminUser[] | null>(null);
  const [trips, setTrips] = useState<TripSummary[] | null>(null);
  const [picked, setPicked] = useState<AdminUserDetail | null>(null);
  const [viewing, setViewing] = useState<number | null>(null);
  const [error, setError] = useState("");
  function fail(e: unknown) {
    if (e instanceof AuthError) return expired();
    setError((e as Error).message);
  }
  useEffect(() => {
    if (user && user.role !== "admin") router.replace("/dashboard");
  }, [user, router]);
  function loadStats() {
    adminStats().then(setStats).catch(fail);
  }
  useEffect(() => {
    if (!user || user?.role !== "admin") return;
    loadStats();
  }, [user?.id, user?.role]);
  useEffect(() => {
    if (!user || user?.role !== "admin") return;
    const t = setTimeout(() => {
      if (tab === "users") adminUsers(q).then(setUsers).catch(fail);
      else adminTrips(q).then(setTrips).catch(fail);
    }, 250);
    return () => clearTimeout(t);
  }, [user?.id, user?.role, tab, q]);
  function openUser(id: number) {
    adminUser(id).then(setPicked).catch(fail);
  }
  async function ban(u: AdminUserDetail) {
    if (
      !u.banned &&
      !window.confirm(`Ban ${u.name} (#${u.id})? They will be signed out and cannot sign in until unbanned.`)
    )
      return;
    try {
      const next = await adminBan(u.id, !u.banned);
      setPicked(next);
      setUsers((old) => (old ?? []).map((x) => (x.id === next.id ? { ...x, banned: next.banned } : x)));
      loadStats();
    } catch (e) {
      fail(e);
    }
  }
  async function remove(u: AdminUserDetail) {
    if (
      !window.confirm(
        `Delete the account of ${u.name} (#${u.id}) with all ${u.trips} itineraries? This cannot be undone.`,
      )
    )
      return;
    try {
      await adminDelete(u.id);
      setPicked(null);
      setUsers((old) => (old ?? []).filter((x) => x.id !== u.id));
      loadStats();
    } catch (e) {
      fail(e);
    }
  }
  if (!user || user.role !== "admin")
    return (
      <div className="page">
        <TopBar user={user} />
        <p className="muted center pad">Checking access</p>
      </div>
    );
  return (
    <div className="page">
      <TopBar user={user} />
      <main className="admin">
        <div className="row-between">
          <h1>Admin panel</h1>
          {stats && (
            <dl className="tiles">
              <div>
                <dt>Users</dt>
                <dd>{stats.users}</dd>
              </div>
              <div>
                <dt>Banned</dt>
                <dd>{stats.banned}</dd>
              </div>
              <div>
                <dt>Itineraries</dt>
                <dd>{stats.itineraries}</dd>
              </div>
            </dl>
          )}
        </div>
        {error && (
          <p className="error" role="alert">
            {error}
          </p>
        )}
        <div className="admin-bar">
          <div className="tabs small-tabs" role="tablist">
            <button type="button" role="tab" aria-selected={tab === "users"} onClick={() => setTab("users")}>
              Users
            </button>
            <button type="button" role="tab" aria-selected={tab === "trips"} onClick={() => setTab("trips")}>
              Itineraries
            </button>
          </div>
          <label className="search">
            <span className="sr-only">Search</span>
            <input
              type="search"
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder={
                tab === "users" ? "Search by user ID, name or email" : "Search by user ID, itinerary ID, city or name"
              }
            />
          </label>
        </div>
        <div className={`admin-grid ${picked && tab === "users" ? "with-detail" : ""}`}>
          <div className="card table-card">
            {tab === "users" ? (
              users === null ? (
                <p className="muted">Loading</p>
              ) : users.length === 0 ? (
                <p className="muted">No users match "{q}".</p>
              ) : (
                <table className="table">
                  <thead>
                    <tr>
                      <th>User ID</th>
                      <th>Name</th>
                      <th className="hide-sm">Email</th>
                      <th>Trips</th>
                      <th>Status</th>
                    </tr>
                  </thead>
                  <tbody>
                    {users.map((u) => (
                      <tr
                        key={u.id}
                        className={picked?.id === u.id ? "picked" : ""}
                        onClick={() => openUser(u.id)}
                        tabIndex={0}
                        onKeyDown={(e) => e.key === "Enter" && openUser(u.id)}
                      >
                        <td className="uid">#{u.id}</td>
                        <td>
                          {u.name}
                          {u.role === "admin" && <span className="tag">admin</span>}
                        </td>
                        <td className="hide-sm muted">{u.email}</td>
                        <td>{u.trips}</td>
                        <td>
                          {u.banned ? (
                            <span className="status banned">Banned</span>
                          ) : (
                            <span className="status active">Active</span>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )
            ) : trips === null ? (
              <p className="muted">Loading</p>
            ) : trips.length === 0 ? (
              <p className="muted">No itineraries match "{q}".</p>
            ) : (
              <ul className="all-trips">
                {trips.map((t) => (
                  <li key={t.id}>
                    <div className="trip-main">
                      <p className="row-title">
                        {t.origin} to {t.destination} itinerary
                      </p>
                      <p className="muted small">
                        {shortDate(t.start_date)} to {shortDate(t.end_date)}, {t.travellers} traveller
                        {t.travellers > 1 ? "s" : ""}. Itinerary #{t.id}, saved {shortDate(t.updated)}
                      </p>
                    </div>
                    <dl className="trip-money">
                      <div>
                        <dt>Amount</dt>
                        <dd>{rupees(t.total_cost)}</dd>
                      </div>
                      <div>
                        <dt>Budget</dt>
                        <dd>{rupees(t.budget_inr)}</dd>
                      </div>
                    </dl>
                    <p className="trip-by small">
                      Created by{" "}
                      <button
                        type="button"
                        className="link"
                        onClick={() => {
                          setTab("users");
                          setQ(String(t.user_id));
                          openUser(t.user_id);
                        }}
                      >
                        user #{t.user_id}
                      </button>
                      <br />
                      <span className="muted">{t.user_name}</span>
                    </p>
                    <button type="button" className="btn-secondary small-btn" onClick={() => setViewing(t.id)}>
                      View
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>
          {picked && tab === "users" && (
            <aside className="card detail" aria-label="User details">
              <div className="row-between">
                <h2>{picked.name}</h2>
                <button type="button" className="btn-ghost" onClick={() => setPicked(null)}>
                  Close
                </button>
              </div>
              <dl className="facts">
                <div>
                  <dt>User ID</dt>
                  <dd className="uid">#{picked.id}</dd>
                </div>
                <div>
                  <dt>Email</dt>
                  <dd>{picked.email}</dd>
                </div>
                <div>
                  <dt>Date of birth</dt>
                  <dd>
                    {shortDate(picked.birth_date)} {picked.birth_date.slice(0, 4)}
                  </dd>
                </div>
                <div>
                  <dt>Joined</dt>
                  <dd>{shortDate(picked.created)}</dd>
                </div>
                <div>
                  <dt>Last sign in</dt>
                  <dd>{picked.last_login ? shortDate(picked.last_login) : "Never"}</dd>
                </div>
                <div>
                  <dt>Status</dt>
                  <dd>
                    {picked.banned ? (
                      <span className="status banned">Banned</span>
                    ) : (
                      <span className="status active">Active</span>
                    )}
                  </dd>
                </div>
              </dl>
              {picked.id !== user.id && (
                <div className="actions-row">
                  <button
                    type="button"
                    className={picked.banned ? "btn-secondary" : "btn-danger-ghost"}
                    onClick={() => ban(picked)}
                  >
                    {picked.banned ? "Unban user" : "Ban user"}
                  </button>
                  <button type="button" className="btn-danger" onClick={() => remove(picked)}>
                    Delete account
                  </button>
                </div>
              )}
              <h3>Itineraries ({picked.trips})</h3>
              {picked.itineraries.length === 0 ? (
                <p className="muted">This user has not made any itineraries yet.</p>
              ) : (
                <ul className="trip-list">
                  {picked.itineraries.map((t) => (
                    <li key={t.id}>
                      <div>
                        <p className="row-title">
                          {t.origin} to {t.destination}
                        </p>
                        <p className="muted small">
                          #{t.id}, {shortDate(t.start_date)} to {shortDate(t.end_date)}, {rupees(t.total_cost)}
                        </p>
                      </div>
                      <button type="button" className="btn-secondary small-btn" onClick={() => setViewing(t.id)}>
                        View
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </aside>
          )}
        </div>
      </main>
      {viewing !== null && <TripViewer id={viewing} onClose={() => setViewing(null)} />}
    </div>
  );
}

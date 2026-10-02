import React, { useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import { api, post, setCsrf } from "./api";
import { AdminPage, Entity } from "./AdminPage";
import { ErrorBox, roleNames } from "./components";
import { HistoryPage } from "./HistoryPage";
import { ImportPage } from "./ImportPage";
import { PrintPage } from "./PrintPage";
import { SettingsPage } from "./SettingsPage";
import { Settings, User } from "./types";
import "./style.css";

function Login({ onLogin }: { onLogin: (user: User) => void }) {
  const [username, setUsername] = useState(""),
    [password, setPassword] = useState(""),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false);
  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const result = await post<{ user: User; csrf_token: string }>(
        "/auth/login",
        { username, password },
      );
      setCsrf(result.csrf_token);
      onLogin(result.user);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="login-screen">
      <div className="login-brand">
        <span className="brand-icon">▥</span>
        <span>pi_printserver</span>
      </div>
      <form onSubmit={submit} className="card login-card">
        <p className="eyebrow">INTERNÍ TISK ŠTÍTKŮ</p>
        <h1>Přihlášení</h1>
        <p className="muted">
          Síťové Zebra tiskárny · centrální katalog · audit
        </p>
        <ErrorBox error={error} />
        <fieldset className="fields" disabled={busy}>
          <label>
            Uživatelské jméno
            <input
              autoFocus
              required
              autoComplete="username"
              value={username}
              maxLength={80}
              onChange={(e) => setUsername(e.target.value)}
            />
          </label>
          <label>
            Heslo
            <input
              type="password"
              required
              autoComplete="current-password"
              value={password}
              maxLength={256}
              onChange={(e) => setPassword(e.target.value)}
            />
          </label>
        </fieldset>
        <button className="full" disabled={busy}>
          {busy ? "Přihlašování…" : "Přihlásit se"}
        </button>
      </form>
    </div>
  );
}

function App() {
  const [user, setUser] = useState<User | null>(null),
    [settings, setSettings] = useState<Settings | null>(null),
    [loading, setLoading] = useState(true),
    [error, setError] = useState("");
  const [page, setPage] = useState(location.hash.slice(1) || "print");
  useEffect(() => {
    api<{ user: User; csrf_token: string }>("/auth/me")
      .then((result) => {
        setUser(result.user);
        setCsrf(result.csrf_token);
      })
      .catch(() => {})
      .finally(() => setLoading(false));
    const navigate = () => setPage(location.hash.slice(1) || "print");
    const expire = () => {
      setUser(null);
      setSettings(null);
      setCsrf("");
    };
    window.addEventListener("hashchange", navigate);
    window.addEventListener("session-expired", expire);
    return () => {
      window.removeEventListener("hashchange", navigate);
      window.removeEventListener("session-expired", expire);
    };
  }, []);
  useEffect(() => {
    if (user) {
      api<Settings>("/settings")
        .then((value) => {
          setSettings(value);
          setError("");
        })
        .catch((e) => setError(e.message));
    }
  }, [user]);
  async function logout() {
    try {
      await post("/auth/logout");
      setCsrf("");
      setUser(null);
      setSettings(null);
    } catch (e) {
      setError((e as Error).message);
    }
  }
  if (loading) return <div className="login-screen">Načítání…</div>;
  if (!user) return <Login onLogin={setUser} />;
  const editing = user.role === "admin" || user.role === "engineer";
  const pages = [
    { id: "print", label: "Tisk štítků", icon: "▥" },
    { id: "history", label: "Historie", icon: "◷" },
    ...(editing
      ? [
          { id: "products", label: "Produkty", icon: "▦" },
          { id: "templates", label: "Šablony", icon: "▤" },
        ]
      : []),
    ...(user.role === "admin"
      ? [
          { id: "printers", label: "Tiskárny", icon: "▣" },
          { id: "users", label: "Uživatelé", icon: "♙" },
          { id: "settings", label: "Nastavení", icon: "⚙" },
          { id: "import", label: "Import katalogu", icon: "⇥" },
        ]
      : []),
  ];
  const permitted = pages.some((p) => p.id === page);
  return (
    <div className="app-shell">
      <aside className="sidebar">
        <a className="brand" href="#print">
          <span className="brand-icon">▥</span>pi_printserver
        </a>
        <small className="sidebar-caption">CENTRÁLNÍ TISK</small>
        <nav aria-label="Hlavní navigace">
          {pages.map((item) => (
            <a
              key={item.id}
              href={"#" + item.id}
              className={page === item.id ? "active" : ""}
            >
              <span aria-hidden="true">{item.icon}</span>
              {item.label}
            </a>
          ))}
        </nav>
        <div className="sidebar-footer">
          <strong>{user.display_name || user.username}</strong>
          <small>{roleNames[user.role]}</small>
          <button className="logout" onClick={logout}>
            Odhlásit se
          </button>
        </div>
      </aside>
      <div className="workspace">
        <header className="topbar">
          <span>Interní síť · Zebra / ZPL</span>
          <span>{user.username}</span>
        </header>
        <main>
          <ErrorBox error={error} />
          {!settings ? (
            <>
              <p>Načítání nastavení…</p>
              {error && (
                <button
                  onClick={() =>
                    api<Settings>("/settings")
                      .then(setSettings)
                      .catch((e) => setError(e.message))
                  }
                >
                  Zkusit znovu
                </button>
              )}
            </>
          ) : !permitted ? (
            <div className="card">
              <h1>Nedostatečné oprávnění</h1>
              <a href="#print">Přejít na tisk</a>
            </div>
          ) : page === "print" ? (
            <PrintPage key={user.id} user={user} settings={settings} />
          ) : page === "history" ? (
            <HistoryPage user={user} settings={settings} />
          ) : page === "settings" ? (
            <SettingsPage settings={settings} onSave={setSettings} />
          ) : page === "import" ? (
            <ImportPage />
          ) : (
            <AdminPage key={page} entity={page as Entity} />
          )}
        </main>
        <footer className="app-footer">
          Odesláno = data doručena tiskovému endpointu. Fyzický výstup ověřte na
          tiskárně.
        </footer>
      </div>
    </div>
  );
}

createRoot(document.getElementById("root")!).render(<App />);

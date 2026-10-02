import React, { useState } from "react";
import { api, post } from "./api";
import { ErrorBox } from "./components";
import { ImportRun } from "./types";

export function ImportPage() {
  const [file, setFile] = useState<File | null>(null),
    [copy, setCopy] = useState(false),
    [run, setRun] = useState<ImportRun | null>(null),
    [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  async function dry(e: React.FormEvent) {
    e.preventDefault();
    if (!file) return;
    setBusy(true);
    setError("");
    setRun(null);
    const form = new FormData();
    form.set("file", file);
    form.set("confirm_copy", String(copy));
    try {
      setRun(
        await api<ImportRun>("/import/dry-run", { method: "POST", body: form }),
      );
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function execute() {
    if (!run) return;
    setBusy(true);
    setError("");
    try {
      const result = await post<ImportRun>(`/import/${run.id}/execute`);
      setRun({ ...run, ...result });
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      <div className="page-heading">
        <div>
          <p className="eyebrow">MIGRACE KATALOGU</p>
          <h1>Import z printserver_win</h1>
          <p>Nahraná kopie → dry-run → kontrola → import v jedné transakci.</p>
        </div>
      </div>
      <section className="card narrow">
        <form onSubmit={dry} className="fields">
          <p>
            Připravte samostatnou zálohu SQLite pomocí SQLite backup nebo
            příkazu VACUUM INTO. Původní aplikace a její živá databáze se
            nemění.
          </p>
          <label>
            Kopie SQLite databáze (max. 20 MiB)
            <input
              type="file"
              accept=".db,.sqlite,.sqlite3"
              required
              disabled={busy}
              onChange={(e) => {
                setFile(e.target.files?.[0] || null);
                setRun(null);
              }}
            />
          </label>
          <label className="check">
            <input
              type="checkbox"
              checked={copy}
              disabled={busy}
              onChange={(e) => setCopy(e.target.checked)}
            />
            Potvrzuji, že nahrávám výslovně připravenou kopii databáze.
          </label>
          <button disabled={busy || !copy || !file}>
            {busy ? "Zpracování…" : "Spustit dry-run"}
          </button>
        </form>
        <ErrorBox error={error} />
      </section>
      {run && (
        <section className="card import-report">
          <h2>{run.executed_at ? "Import dokončen" : "Výsledek dry-run"}</h2>
          <p className="mono break">SHA-256 kopie: {run.source_hash}</p>
          <div className="stats">
            {[
              ["Nové šablony", run.report.templates_create],
              ["Existující šablony", run.report.templates_existing],
              ["Nové produkty", run.report.products_create],
              ["Přeskočené produkty", run.report.products_skip],
            ].map(([label, items]) => (
              <div key={label as string}>
                <strong>{(items as string[]).length}</strong>
                <span>{label as string}</span>
              </div>
            ))}
          </div>
          <p>
            Existující produkty se nepřepisují. Stejnojmenná šablona musí mít
            shodný obsah. Účty, hesla, výroba a kiosk historie se nepřenášejí;
            síťové tiskárny se konfigurují samostatně.
          </p>
          {run.report.errors.map((e, i) => (
            <ErrorBox key={i} error={e} />
          ))}
          {run.report.warnings.length > 0 && (
            <details open>
              <summary>Upozornění</summary>
              <ul>
                {run.report.warnings.map((w, i) => (
                  <li key={i}>{w}</li>
                ))}
              </ul>
            </details>
          )}
          <details>
            <summary>Seznam záznamů</summary>
            <pre>{JSON.stringify(run.report, null, 2)}</pre>
          </details>
          {run.executed_at ? (
            <div className="alert success" role="status">
              Katalog importován{" "}
              {new Date(run.executed_at).toLocaleString("cs-CZ")}.
            </div>
          ) : (
            <>
              <p className="muted">
                Dry-run platí jednu hodinu. Změna cílového katalogu vyžaduje
                nový dry-run.
              </p>
              <button
                disabled={busy || run.report.errors.length > 0}
                onClick={execute}
              >
                {busy ? "Importování…" : "Potvrdit a provést import"}
              </button>
            </>
          )}
        </section>
      )}
    </>
  );
}

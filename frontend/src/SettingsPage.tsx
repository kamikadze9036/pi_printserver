import React, { useState } from "react";
import { put } from "./api";
import { ErrorBox } from "./components";
import { Settings } from "./types";

export function SettingsPage({
  settings,
  onSave,
}: {
  settings: Settings;
  onSave: (value: Settings) => void;
}) {
  const [data, setData] = useState(settings),
    [reasons, setReasons] = useState(settings.reasons.join("\n")),
    [busy, setBusy] = useState(false),
    [error, setError] = useState(""),
    [saved, setSaved] = useState(false);
  async function save(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    setSaved(false);
    try {
      const value = await put<Settings>("/settings", {
        ...data,
        reasons: reasons
          .split("\n")
          .map((s) => s.trim())
          .filter(Boolean),
      });
      onSave(value);
      setSaved(true);
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
          <p className="eyebrow">ADMINISTRACE</p>
          <h1>Nastavení</h1>
          <p>Limity a důvody tisku se ověřují také na serveru.</p>
        </div>
      </div>
      <form className="card narrow fields" onSubmit={save}>
        <ErrorBox error={error} />
        {saved && <div className="alert success">Nastavení uloženo.</div>}
        <fieldset disabled={busy} className="fields">
          <label>
            Výchozí množství
            <input
              type="number"
              required
              min="1"
              max={data.max_quantity}
              value={data.default_quantity}
              onChange={(e) =>
                setData({ ...data, default_quantity: Number(e.target.value) })
              }
            />
          </label>
          <label>
            Maximální množství
            <input
              type="number"
              required
              min="1"
              max="99999"
              value={data.max_quantity}
              onChange={(e) =>
                setData({ ...data, max_quantity: Number(e.target.value) })
              }
            />
          </label>
          <label className="check">
            <input
              type="checkbox"
              checked={data.reason_required}
              onChange={(e) =>
                setData({ ...data, reason_required: e.target.checked })
              }
            />
            Důvod tisku je povinný
          </label>
          <label>
            Důvody (jeden na řádek)
            <textarea
              rows={8}
              required
              value={reasons}
              onChange={(e) => setReasons(e.target.value)}
            />
          </label>
        </fieldset>
        <button disabled={busy}>
          {busy ? "Ukládání…" : "Uložit nastavení"}
        </button>
      </form>
    </>
  );
}

import React, { useEffect, useState } from "react";
import { api, post, requestToken } from "./api";
import { Job, Preview, Printer, Settings, User } from "./types";

export const roleNames = {
  admin: "Administrátor",
  engineer: "Procesní inženýr / technik",
  team_leader: "Team leader",
  viewer: "Prohlížení",
};
export const statusNames = {
  queued: "Zpracovává se",
  sent: "Odesláno",
  failed: "Chyba",
};
export function ErrorBox({ error }: { error: string }) {
  return error ? (
    <div className="alert error" role="alert">
      {error}
    </div>
  ) : null;
}
export function LabelPreview({ preview }: { preview: Preview | null }) {
  return (
    <div className="preview-area">
      {preview ? (
        <>
          <img
            alt="Náhled štítku"
            src={
              "data:image/svg+xml;charset=utf-8," +
              encodeURIComponent(preview.svg)
            }
          />
          <small>
            Pozice a QR podle rendereru; font v náhledu je orientační.
          </small>
          <details>
            <summary>Generované ZPL</summary>
            <pre>{preview.zpl}</pre>
          </details>
        </>
      ) : (
        <div className="empty">Vyberte produkt a tiskárnu pro náhled.</div>
      )}
    </div>
  );
}
export function JobResult({
  job,
  onRefresh,
}: {
  job: Job;
  onRefresh?: (job: Job) => void;
}) {
  const [error, setError] = useState("");
  useEffect(() => {
    if (job.status !== "queued" || !onRefresh) return;
    const timer = window.setInterval(
      () =>
        api<Job>("/print-jobs/" + job.id)
          .then(onRefresh)
          .catch((e) => setError(e.message)),
      2000,
    );
    return () => clearInterval(timer);
  }, [job.id, job.status, onRefresh]);
  return (
    <div className={"job-result " + job.status} role="status">
      <strong>
        {statusNames[job.status]} · {job.quantity} ks
      </strong>
      <p>
        {job.status === "sent"
          ? "Data byla odeslána na tiskárnu. Výroba fyzického štítku není potvrzena."
          : job.status === "queued"
            ? "Požadavek se zpracovává. Nevytvářejte další tisk."
            : job.error}
      </p>
      {job.status === "failed" && (
        <small>
          Před opakováním zkontrolujte tiskárnu. Automatický retry se neprovádí.
        </small>
      )}
      <small>Job: {job.id}</small>
      <ErrorBox error={error} />
    </div>
  );
}
export function JobDetail({
  job,
  user,
  settings,
  printers,
  onClose,
}: {
  job: Job;
  user: User;
  settings: Settings;
  printers: Printer[];
  onClose: () => void;
}) {
  const pendingKey = `pending-reprint-${user.id}-${job.id}`;
  const [pending, setPending] = useState<Record<string, unknown> | null>(() => {
    try {
      return JSON.parse(sessionStorage.getItem(pendingKey) || "null");
    } catch {
      return null;
    }
  });
  const [quantity, setQuantity] = useState(
      Number(pending?.quantity || job.quantity),
    ),
    [printer, setPrinter] = useState(
      Number(
        pending?.printer_id || job.printer_snapshot.id || printers[0]?.id || 0,
      ),
    );
  const [reason, setReason] = useState(
      String(pending?.reason || settings.reasons[0] || ""),
    ),
    [note, setNote] = useState(String(pending?.note || "")),
    [reference, setReference] = useState(String(pending?.reference || ""));
  const [result, setResult] = useState<Job | null>(null),
    [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  async function reprint(e: React.FormEvent) {
    e.preventDefault();
    if (busy) return;
    setBusy(true);
    setError("");
    const data = pending || {
      printer_id: printer,
      quantity,
      reason,
      note,
      reference,
      idempotency_key: requestToken(),
    };
    setPending(data);
    sessionStorage.setItem(pendingKey, JSON.stringify(data));
    try {
      setResult(await post<Job>(`/print-jobs/${job.id}/reprint`, data));
      setPending(null);
      sessionStorage.removeItem(pendingKey);
    } catch (e) {
      setError(
        (e as Error).message +
          " Požadavek je uložený; ověřte jej stejným tokenem.",
      );
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="modal-backdrop">
      <section className="modal large" aria-label="Detail tiskové úlohy">
        <div className="row spread">
          <h2>Detail úlohy</h2>
          <button className="secondary" onClick={onClose} disabled={busy}>
            Zavřít
          </button>
        </div>
        <JobResult job={job} />
        <dl className="detail-grid">
          <dt>Produkt</dt>
          <dd>
            {job.product_snapshot.product_code} ·{" "}
            {job.product_snapshot.description}
          </dd>
          <dt>Operátor</dt>
          <dd>
            {job.user_snapshot.display_name || job.user_snapshot.username}
          </dd>
          <dt>Tiskárna</dt>
          <dd>
            {job.printer_snapshot.name} · {job.printer_snapshot.host}:
            {job.printer_snapshot.port}
          </dd>
          <dt>Šablona</dt>
          <dd>{job.template_snapshot.name}</dd>
          <dt>Čas</dt>
          <dd>{new Date(job.created_at).toLocaleString("cs-CZ")}</dd>
          <dt>Důvod / reference</dt>
          <dd>
            {job.reason} / {job.reference || "—"}
          </dd>
          <dt>Poznámka</dt>
          <dd>{job.note || "—"}</dd>
          <dt>Původní úloha</dt>
          <dd>{job.original_job_id || "—"}</dd>
          <dt>SHA-256 ZPL</dt>
          <dd className="mono break">{job.zpl_hash || "—"}</dd>
        </dl>
        <details>
          <summary>Auditní snapshoty a ZPL</summary>
          <pre>
            {JSON.stringify(
              {
                user: job.user_snapshot,
                product: job.product_snapshot,
                template: job.template_snapshot,
                printer: job.printer_snapshot,
              },
              null,
              2,
            )}
          </pre>
          <pre>{job.zpl || "ZPL nebylo vygenerováno."}</pre>
        </details>
        {user.role !== "viewer" &&
          job.status !== "queued" &&
          !!job.zpl &&
          job.product_snapshot.product_code !== "PRINTER TEST" && (
            <form onSubmit={reprint}>
              <h3>Opakovat tisk jako novou úlohu</h3>
              <p className="muted">
                Použijí se původní data produktu a šablony. Datum, čas a
                operátor budou aktuální.
              </p>
              <fieldset
                disabled={busy || !!pending || !!result}
                className="fields"
              >
                <label>
                  Tiskárna
                  <select
                    aria-label="Tiskárna"
                    value={printer}
                    onChange={(e) => setPrinter(Number(e.target.value))}
                  >
                    {printers.map((p) => (
                      <option key={p.id} value={p.id}>
                        {p.name}
                        {p.active ? "" : " (neaktivní)"}
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  Množství
                  <input
                    type="number"
                    min="1"
                    max={settings.max_quantity}
                    required
                    value={quantity}
                    onChange={(e) => setQuantity(Number(e.target.value))}
                  />
                </label>
                <label>
                  Důvod
                  <select
                    aria-label="Důvod"
                    value={reason}
                    required={settings.reason_required}
                    onChange={(e) => setReason(e.target.value)}
                  >
                    {settings.reasons.map((r) => (
                      <option key={r}>{r}</option>
                    ))}
                  </select>
                </label>
                <label>
                  Reference
                  <input
                    value={reference}
                    maxLength={200}
                    onChange={(e) => setReference(e.target.value)}
                  />
                </label>
                <label>
                  Poznámka
                  <textarea
                    value={note}
                    maxLength={4000}
                    onChange={(e) => setNote(e.target.value)}
                  />
                </label>
              </fieldset>
              <ErrorBox error={error} />
              {!result && (
                <button disabled={busy || !printer}>
                  {busy
                    ? "Odesílání…"
                    : pending
                      ? "Ověřit stejný požadavek"
                      : `Opakovat tisk · ${quantity} ks`}
                </button>
              )}
            </form>
          )}
        {result && <JobResult job={result} onRefresh={setResult} />}
      </section>
    </div>
  );
}

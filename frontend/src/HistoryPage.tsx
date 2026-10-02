import React, { useEffect, useState } from "react";
import { all, api } from "./api";
import { ErrorBox, JobDetail, statusNames } from "./components";
import { Job, Printer, Settings, User } from "./types";

export function HistoryPage({
  user,
  settings,
}: {
  user: User;
  settings: Settings;
}) {
  const [jobs, setJobs] = useState<Job[]>([]),
    [selected, setSelected] = useState<Job | null>(null),
    [printers, setPrinters] = useState<Printer[]>([]);
  const [query, setQuery] = useState(""),
    [status, setStatus] = useState(""),
    [since, setSince] = useState(""),
    [until, setUntil] = useState("");
  const [offset, setOffset] = useState(0),
    [error, setError] = useState(""),
    [reload, setReload] = useState(0),
    [loading, setLoading] = useState(false);
  useEffect(() => {
    all<Printer>("/printers")
      .then(setPrinters)
      .catch((e) => setError(e.message));
  }, []);
  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    const params = new URLSearchParams({
      q: query,
      limit: "50",
      offset: String(offset),
    });
    if (status) params.set("status", status);
    if (since) params.set("since", new Date(since).toISOString());
    if (until) params.set("until", new Date(until).toISOString());
    api<Job[]>("/print-jobs?" + params)
      .then((rows) => {
        if (!cancelled) {
          setJobs(rows);
          setError("");
        }
      })
      .catch((e) => {
        if (!cancelled) setError(e.message);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [query, status, since, until, offset, reload]);
  async function detail(job: Job) {
    try {
      setSelected(await api<Job>("/print-jobs/" + job.id));
    } catch (e) {
      setError((e as Error).message);
    }
  }
  return (
    <>
      <div className="page-heading">
        <div>
          <p className="eyebrow">AUDIT</p>
          <h1>Historie tisku</h1>
          <p>Snapshoty produktů, šablon a tiskáren zůstávají zachovány.</p>
        </div>
        <button className="secondary" onClick={() => setReload(reload + 1)}>
          Obnovit
        </button>
      </div>
      <div className="card">
        <div className="filters">
          <label>
            Kód produktu
            <input
              value={query}
              onChange={(e) => {
                setQuery(e.target.value);
                setOffset(0);
              }}
            />
          </label>
          <label>
            Stav
            <select
              aria-label="Stav"
              value={status}
              onChange={(e) => {
                setStatus(e.target.value);
                setOffset(0);
              }}
            >
              <option value="">Všechny stavy</option>
              {Object.entries(statusNames).map(([key, value]) => (
                <option key={key} value={key}>
                  {value}
                </option>
              ))}
            </select>
          </label>
          <label>
            Od
            <input
              type="datetime-local"
              value={since}
              onChange={(e) => {
                setSince(e.target.value);
                setOffset(0);
              }}
            />
          </label>
          <label>
            Do
            <input
              type="datetime-local"
              value={until}
              onChange={(e) => {
                setUntil(e.target.value);
                setOffset(0);
              }}
            />
          </label>
        </div>
        <ErrorBox error={error} />
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>Čas</th>
                <th>Produkt</th>
                <th>Operátor</th>
                <th>Tiskárna</th>
                <th>Počet</th>
                <th>Důvod</th>
                <th>Stav</th>
                <th>Detail</th>
              </tr>
            </thead>
            <tbody>
              {jobs.map((job) => (
                <tr key={job.id}>
                  <td>{new Date(job.created_at).toLocaleString("cs-CZ")}</td>
                  <td>
                    <strong>{job.product_snapshot.product_code || "—"}</strong>
                    {job.original_job_id && <small>Opakovaný tisk</small>}
                  </td>
                  <td>{job.user_snapshot.username}</td>
                  <td>
                    {job.printer_snapshot.name || `#${job.printer_snapshot.id}`}
                  </td>
                  <td>{job.quantity}</td>
                  <td>{job.reason || "—"}</td>
                  <td>
                    <span className={"badge " + job.status}>
                      {statusNames[job.status]}
                    </span>
                  </td>
                  <td>
                    <button
                      className="secondary small"
                      onClick={() => detail(job)}
                    >
                      Otevřít
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {!jobs.length && (
          <p className="empty">
            {loading ? "Načítání…" : "Žádné tiskové úlohy pro tento filtr."}
          </p>
        )}
        <div className="row spread pagination">
          <button
            className="secondary"
            disabled={!offset || loading}
            onClick={() => setOffset(Math.max(0, offset - 50))}
          >
            Předchozí
          </button>
          <span>
            {offset + 1}–{offset + jobs.length}
          </span>
          <button
            className="secondary"
            disabled={jobs.length < 50 || loading}
            onClick={() => setOffset(offset + 50)}
          >
            Další
          </button>
        </div>
      </div>
      {selected && (
        <JobDetail
          job={selected}
          user={user}
          settings={settings}
          printers={printers}
          onClose={() => {
            setSelected(null);
            setReload(reload + 1);
          }}
        />
      )}
    </>
  );
}

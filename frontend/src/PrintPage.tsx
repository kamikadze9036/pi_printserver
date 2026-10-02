import React, { useEffect, useRef, useState } from "react";
import { all, api, post, requestToken } from "./api";
import { ErrorBox, JobResult, LabelPreview } from "./components";
import {
  Job,
  Preview,
  Printer,
  PrintRequest,
  Product,
  Settings,
  User,
} from "./types";

function pendingPrint(userId: number): PrintRequest | null {
  try {
    return JSON.parse(
      sessionStorage.getItem("pending-print-" + userId) || "null",
    );
  } catch {
    return null;
  }
}

export function PrintPage({
  user,
  settings,
}: {
  user: User;
  settings: Settings;
}) {
  const [query, setQuery] = useState(""),
    [products, setProducts] = useState<Product[]>([]),
    [printers, setPrinters] = useState<Printer[]>([]);
  const [product, setProduct] = useState<Product | null>(null),
    [printer, setPrinter] = useState(0),
    [quantity, setQuantity] = useState(settings.default_quantity);
  const [reason, setReason] = useState(settings.reasons[0] || ""),
    [note, setNote] = useState(""),
    [reference, setReference] = useState("");
  const [preview, setPreview] = useState<Preview | null>(null),
    [previewError, setPreviewError] = useState(""),
    [error, setError] = useState("");
  const [busy, setBusy] = useState(false),
    [job, setJob] = useState<Job | null>(null),
    [pending, setPending] = useState(() => pendingPrint(user.id));
  const submitting = useRef(false);
  useEffect(() => {
    all<Printer>("/printers?active=true")
      .then((rows) => {
        setPrinters(rows);
        setPrinter(rows[0]?.id || 0);
      })
      .catch((e) => setError(e.message));
  }, []);
  useEffect(() => {
    const controller = new AbortController();
    const timer = setTimeout(
      () =>
        api<Product[]>(
          `/products?active=true&limit=100&q=${encodeURIComponent(query)}`,
          { signal: controller.signal },
        )
          .then(setProducts)
          .catch((e) => {
            if (e.name !== "AbortError") setError(e.message);
          }),
      180,
    );
    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [query]);
  useEffect(() => {
    setPreview(null);
    setPreviewError("");
    if (
      !product ||
      !printer ||
      quantity < 1 ||
      quantity > settings.max_quantity
    )
      return;
    const controller = new AbortController();
    const timer = setTimeout(
      () =>
        api<Preview>("/preview", {
          method: "POST",
          body: JSON.stringify({
            product_id: product.id,
            printer_id: printer,
            quantity,
          }),
          signal: controller.signal,
        })
          .then(setPreview)
          .catch((e) => {
            if (e.name !== "AbortError") setPreviewError(e.message);
          }),
      180,
    );
    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [product, printer, quantity, settings.max_quantity]);
  function choose(item: Product) {
    setProduct(item);
    if (printers.some((p) => p.id === item.preferred_printer_id))
      setPrinter(item.preferred_printer_id!);
    setJob(null);
  }
  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (submitting.current || (!product && !pending)) return;
    submitting.current = true;
    setBusy(true);
    setError("");
    const data = pending || {
      product_id: product!.id,
      printer_id: printer,
      quantity,
      reason,
      note,
      reference,
      idempotency_key: requestToken(),
    };
    setPending(data);
    sessionStorage.setItem("pending-print-" + user.id, JSON.stringify(data));
    try {
      const result = await post<Job>("/print-jobs", data);
      setJob(result);
      setPending(null);
      sessionStorage.removeItem("pending-print-" + user.id);
    } catch (e) {
      setError(
        (e as Error).message +
          " Požadavek zůstává uložený; ověřte jej stejným tokenem.",
      );
    } finally {
      submitting.current = false;
      setBusy(false);
    }
  }
  const frozen = busy || !!pending || !!job;
  return (
    <>
      <div className="page-heading">
        <div>
          <p className="eyebrow">PROVOZ</p>
          <h1>Tisk štítků</h1>
          <p>Vyberte produkt, tiskárnu a počet stejných štítků.</p>
        </div>
        <span className="pill">ZPL · TCP/9100</span>
      </div>
      <ErrorBox error={error} />
      {pending && (
        <div className="alert warning">
          Uložený požadavek: produkt #{pending.product_id}, {pending.quantity}{" "}
          ks. Ověřte jej tlačítkem níže; stejný token další tisk neodešle.
        </div>
      )}
      <div className="print-layout">
        <section className="card product-picker">
          <h2>1. Produkt</h2>
          <label>
            Vyhledat produkt
            <input
              autoFocus
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Kód nebo popis…"
              disabled={!!frozen}
            />
          </label>
          <div className="product-results">
            {products.length === 0 ? (
              <p className="empty">
                Žádné produkty. Administrátor může vytvořit nebo importovat
                katalog.
              </p>
            ) : (
              products.map((item) => (
                <button
                  key={item.id}
                  className={
                    "product-option " +
                    (item.id === product?.id ? "selected" : "")
                  }
                  onClick={() => choose(item)}
                  disabled={!!frozen}
                >
                  <strong>{item.product_code}</strong>
                  <span>
                    {item.description || item.text_content || "Bez popisu"}
                  </span>
                </button>
              ))
            )}
          </div>
          {products.length === 100 && (
            <small>Zobrazeno prvních 100 výsledků. Upřesněte hledání.</small>
          )}
        </section>
        <section className="card">
          <h2>2. Náhled štítku</h2>
          {product && (
            <>
              <h3 className="product-code">{product.product_code}</h3>
              <p>{product.description}</p>
              <dl className="product-data">
                <dt>Text 1</dt>
                <dd>{product.text_content || "—"}</dd>
                <dt>Text 2–4</dt>
                <dd>
                  {[product.text2, product.text3, product.text4]
                    .filter(Boolean)
                    .join(" · ") || "—"}
                </dd>
                <dt>QR data</dt>
                <dd className="break">{product.qr_content || "—"}</dd>
              </dl>
            </>
          )}
          <ErrorBox error={previewError} />
          <LabelPreview preview={preview} />
        </section>
        <section className="card">
          <h2>3. Tisková úloha</h2>
          <form onSubmit={submit}>
            <fieldset
              disabled={!!frozen || user.role === "viewer"}
              className="fields"
            >
              <label>
                Tiskárna
                <select
                  aria-label="Tiskárna"
                  value={printer}
                  required
                  onChange={(e) => setPrinter(Number(e.target.value))}
                >
                  <option value="">Vyberte tiskárnu</option>
                  {printers.map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.name}
                      {p.location ? ` · ${p.location}` : ""}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Množství
                <input
                  className="quantity"
                  aria-label="Množství"
                  aria-describedby="quantity-help"
                  type="number"
                  min="1"
                  max={settings.max_quantity}
                  step="1"
                  required
                  value={quantity}
                  onChange={(e) => {
                    setQuantity(Number(e.target.value));
                    setJob(null);
                  }}
                />
                <small id="quantity-help">
                  1–{settings.max_quantity} identických štítků v jedné úloze.
                </small>
              </label>
              <label>
                Důvod
                <select
                  aria-label="Důvod"
                  value={reason}
                  required={settings.reason_required}
                  onChange={(e) => setReason(e.target.value)}
                >
                  {!settings.reason_required && (
                    <option value="">Bez důvodu</option>
                  )}
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
                  placeholder="Zakázka, reklamace…"
                  onChange={(e) => setReference(e.target.value)}
                />
              </label>
              <label>
                Poznámka
                <textarea
                  value={note}
                  maxLength={4000}
                  rows={3}
                  onChange={(e) => setNote(e.target.value)}
                />
              </label>
            </fieldset>
            <button
              className="print-button"
              type="submit"
              disabled={
                busy ||
                !!job ||
                user.role === "viewer" ||
                (!pending && (!preview || !product || !printer))
              }
            >
              {busy
                ? "Odesílání…"
                : pending
                  ? "Ověřit stejný požadavek"
                  : `TISKNOUT · ${quantity || 0} ks`}
            </button>
            <small className="muted">
              Každá úloha se zaznamená do historie.
            </small>
          </form>
          {job && (
            <>
              <JobResult job={job} onRefresh={setJob} />
              {job.status !== "queued" && (
                <button className="secondary full" onClick={() => setJob(null)}>
                  Připravit novou úlohu
                </button>
              )}
            </>
          )}
        </section>
      </div>
    </>
  );
}

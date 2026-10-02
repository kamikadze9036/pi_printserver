import React, { useEffect, useRef, useState } from "react";
import { all, api, post, put, requestToken } from "./api";
import { ErrorBox, JobResult, LabelPreview, roleNames } from "./components";
import { Element, Job, Preview, Printer, Product, Template } from "./types";

export type Entity = "products" | "templates" | "printers" | "users";
type RecordData = Record<string, unknown> & { id?: number };
type Field = {
  key: string;
  label: string;
  type?: string;
  required?: boolean;
  min?: number;
  max?: number;
  options?: { value: string | number; label: string }[];
};
const names = {
  products: "Produkty",
  templates: "Šablony",
  printers: "Tiskárny",
  users: "Uživatelé",
};
const defaultElements: Element[] = [
  {
    type: "qr",
    name: "QR",
    x: 2,
    y: 2,
    w: 20,
    h: 20,
    font_size: 8,
    content: "{qr_content}",
  },
  {
    type: "text",
    name: "Kód produktu",
    x: 24,
    y: 2,
    w: 34,
    h: 8,
    font_size: 10,
    content: "{product_code}",
  },
  {
    type: "text",
    name: "Text 1",
    x: 24,
    y: 12,
    w: 34,
    h: 8,
    font_size: 7,
    content: "{text_content}",
  },
  {
    type: "text",
    name: "Datum a čas",
    x: 2,
    y: 28,
    w: 56,
    h: 8,
    font_size: 6,
    content: "{date} {time}",
  },
];
const defaults: Record<Entity, RecordData> = {
  products: {
    product_code: "",
    description: "",
    qr_content: "",
    text_content: "",
    text2: "",
    text3: "",
    text4: "",
    side: "both",
    highlight_right: false,
    template_id: null,
    preferred_printer_id: null,
    active: true,
  },
  templates: {
    name: "",
    width_mm: 60,
    height_mm: 40,
    elements: defaultElements,
    active: true,
  },
  printers: {
    name: "",
    host: "",
    port: 9100,
    protocol: "zpl",
    dpi: 203,
    active: true,
    location: "",
    side: "",
    group: "",
  },
  users: {
    username: "",
    display_name: "",
    role: "team_leader",
    active: true,
    password: "",
  },
};

function fields(
  entity: Entity,
  templates: Template[],
  printers: Printer[],
  isNew: boolean,
): Field[] {
  if (entity === "products")
    return [
      { key: "product_code", label: "Kód produktu", required: true, max: 120 },
      { key: "description", label: "Popis", max: 500 },
      {
        key: "template_id",
        label: "Šablona",
        type: "relation",
        options: templates.map((t) => ({
          value: t.id,
          label: t.name + (t.active ? "" : " (neaktivní)"),
        })),
      },
      {
        key: "preferred_printer_id",
        label: "Preferovaná tiskárna",
        type: "relation",
        options: printers.map((p) => ({ value: p.id, label: p.name })),
      },
      { key: "qr_content", label: "QR obsah", type: "textarea", max: 4000 },
      ...["text_content", "text2", "text3", "text4"].map((key, i) => ({
        key,
        label: `Text ${i + 1}`,
        type: "textarea",
        max: 4000,
      })),
      {
        key: "side",
        label: "Strana",
        type: "select",
        options: [
          { value: "both", label: "Obě" },
          { value: "L", label: "Levá" },
          { value: "R", label: "Pravá" },
        ],
      },
      {
        key: "highlight_right",
        label: "Zvýraznit text u pravé strany",
        type: "checkbox",
      },
      { key: "active", label: "Aktivní produkt", type: "checkbox" },
    ];
  if (entity === "templates")
    return [
      { key: "name", label: "Název šablony", required: true, max: 160 },
      {
        key: "width_mm",
        label: "Šířka (mm)",
        type: "number",
        required: true,
        min: 1,
        max: 500,
      },
      {
        key: "height_mm",
        label: "Výška (mm)",
        type: "number",
        required: true,
        min: 1,
        max: 500,
      },
      { key: "active", label: "Aktivní šablona", type: "checkbox" },
    ];
  if (entity === "printers")
    return [
      { key: "name", label: "Název tiskárny", required: true, max: 160 },
      { key: "host", label: "Hostname / IP", required: true, max: 253 },
      {
        key: "port",
        label: "TCP port",
        type: "number",
        required: true,
        min: 1,
        max: 65535,
      },
      {
        key: "dpi",
        label: "DPI",
        type: "numeric-select",
        options: [203, 300, 600].map((n) => ({ value: n, label: String(n) })),
      },
      { key: "location", label: "Umístění", max: 200 },
      { key: "side", label: "Strana", max: 32 },
      { key: "group", label: "Skupina", max: 80 },
      { key: "active", label: "Aktivní tiskárna", type: "checkbox" },
    ];
  return [
    { key: "username", label: "Uživatelské jméno", required: true, max: 80 },
    { key: "display_name", label: "Zobrazované jméno", max: 160 },
    {
      key: "role",
      label: "Role",
      type: "select",
      options: Object.entries(roleNames).map(([value, label]) => ({
        value,
        label,
      })),
    },
    {
      key: "password",
      label: isNew
        ? "Heslo (min. 12 znaků)"
        : "Nové heslo (prázdné = zachovat)",
      type: "password",
      required: isNew,
      min: 12,
      max: 256,
    },
    { key: "active", label: "Aktivní účet", type: "checkbox" },
  ];
}

function FieldInput({
  field,
  value,
  set,
}: {
  field: Field;
  value: unknown;
  set: (value: unknown) => void;
}) {
  const id = "field-" + field.key;
  if (field.type === "checkbox")
    return (
      <label className="check">
        <input
          id={id}
          type="checkbox"
          checked={!!value}
          onChange={(e) => set(e.target.checked)}
        />
        {field.label}
      </label>
    );
  return (
    <label htmlFor={id}>
      {field.label}
      {field.type === "textarea" ? (
        <textarea
          id={id}
          rows={2}
          value={String(value || "")}
          maxLength={field.max}
          onChange={(e) => set(e.target.value)}
        />
      ) : field.options ? (
        <select
          id={id}
          aria-label={field.label}
          value={String(value ?? "")}
          onChange={(e) =>
            set(
              field.type === "relation"
                ? e.target.value
                  ? Number(e.target.value)
                  : null
                : field.type === "numeric-select"
                  ? Number(e.target.value)
                  : e.target.value,
            )
          }
        >
          {field.type === "relation" && <option value="">Bez přiřazení</option>}
          {field.options.map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </select>
      ) : (
        <input
          id={id}
          type={field.type || "text"}
          value={String(value ?? "")}
          required={field.required}
          min={field.type === "number" ? field.min : undefined}
          max={field.type === "number" ? field.max : undefined}
          minLength={field.type === "password" && value ? field.min : undefined}
          maxLength={field.type !== "number" ? field.max : undefined}
          step={field.key.endsWith("_mm") ? "0.1" : "1"}
          autoComplete={field.type === "password" ? "new-password" : "off"}
          onChange={(e) =>
            set(
              field.type === "number" ? Number(e.target.value) : e.target.value,
            )
          }
        />
      )}
    </label>
  );
}

function TemplateEditor({
  data,
  set,
}: {
  data: RecordData;
  set: (data: RecordData) => void;
}) {
  const elements = data.elements as Element[];
  const [preview, setPreview] = useState<Preview | null>(null),
    [error, setError] = useState(""),
    [dpi, setDpi] = useState(203);
  const [sample, setSample] = useState({
    product_code: "FG 001234",
    qr_content: "https://erp.local/fg/001234",
    text_content: "MOTOR SESTAVA",
    text2: "",
    text3: "",
    text4: "",
  });
  useEffect(() => {
    const controller = new AbortController();
    const timer = setTimeout(
      () =>
        api<Preview>("/templates/preview", {
          method: "POST",
          body: JSON.stringify({
            template: { ...data, name: data.name || "Preview" },
            product: sample,
            dpi,
          }),
          signal: controller.signal,
        })
          .then((p) => {
            setPreview(p);
            setError("");
          })
          .catch((e) => {
            if (e.name !== "AbortError") {
              setPreview(null);
              setError(e.message);
            }
          }),
      300,
    );
    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [data, sample, dpi]);
  function change(index: number, key: keyof Element, value: unknown) {
    set({
      ...data,
      elements: elements.map((el, i) =>
        i === index ? { ...el, [key]: value } : el,
      ),
    });
  }
  function add(type: "text" | "qr") {
    set({
      ...data,
      elements: [
        ...elements,
        {
          type,
          name: "Nový prvek",
          x: 2,
          y: 2,
          w: 20,
          h: type === "qr" ? 20 : 8,
          font_size: 8,
          content: type === "qr" ? "{qr_content}" : "{text_content}",
        },
      ],
    });
  }
  return (
    <div className="template-editor">
      <h3>Prvky štítku</h3>
      <p className="muted">
        Souřadnice a rozměry v mm. Proměnné:{" "}
        {
          "{product_code}, {qr_content}, {text_content}/{text1}, {text2}–{text4}, {date}, {time}, {datetime_iso}, {operator}"
        }
        .
      </p>
      {elements.map((el, index) => (
        <details key={index} open className="element-editor">
          <summary>
            {index + 1}. {el.type.toUpperCase()} · {el.name}
          </summary>
          <div className="fields">
            <label>
              Název prvku
              <input
                value={el.name}
                onChange={(e) => change(index, "name", e.target.value)}
              />
            </label>
            <div className="element-numbers">
              {(["x", "y", "w", "h"] as const).map((key) => (
                <label key={key}>
                  {key.toUpperCase()} (mm)
                  <input
                    type="number"
                    min={key === "x" || key === "y" ? 0 : 0.1}
                    max={500}
                    step="0.1"
                    value={el[key]}
                    onChange={(e) => change(index, key, Number(e.target.value))}
                  />
                </label>
              ))}
            </div>
            {el.type === "text" && (
              <label>
                Velikost fontu (body)
                <input
                  type="number"
                  min="1"
                  max="100"
                  step="0.5"
                  value={el.font_size}
                  onChange={(e) =>
                    change(index, "font_size", Number(e.target.value))
                  }
                />
              </label>
            )}
            <label>
              Obsah / proměnné
              <input
                value={el.content}
                maxLength={4000}
                onChange={(e) => change(index, "content", e.target.value)}
              />
            </label>
            <button
              type="button"
              className="danger small"
              onClick={() =>
                set({
                  ...data,
                  elements: elements.filter((_, i) => i !== index),
                })
              }
            >
              Odstranit prvek
            </button>
          </div>
        </details>
      ))}
      <div className="row">
        <button type="button" className="secondary" onClick={() => add("text")}>
          + Text
        </button>
        <button type="button" className="secondary" onClick={() => add("qr")}>
          + QR
        </button>
      </div>
      <h3>Živý náhled</h3>
      <label>
        DPI náhledu
        <select value={dpi} onChange={(e) => setDpi(Number(e.target.value))}>
          {[203, 300, 600].map((n) => (
            <option key={n}>{n}</option>
          ))}
        </select>
      </label>
      <details>
        <summary>Ukázková data pro náhled</summary>
        <div className="fields">
          {Object.keys(sample).map((key) => (
            <label key={key}>
              {key}
              <input
                value={sample[key as keyof typeof sample]}
                onChange={(e) =>
                  setSample({ ...sample, [key]: e.target.value })
                }
              />
            </label>
          ))}
        </div>
      </details>
      <ErrorBox error={error} />
      <LabelPreview preview={preview} />
    </div>
  );
}

export function AdminPage({ entity }: { entity: Entity }) {
  const [rows, setRows] = useState<RecordData[]>([]),
    [data, setData] = useState<RecordData | null>(null),
    [ident, setIdent] = useState<number | null>(null);
  const [templates, setTemplates] = useState<Template[]>([]),
    [printers, setPrinters] = useState<Printer[]>([]),
    [search, setSearch] = useState("");
  const [error, setError] = useState(""),
    [message, setMessage] = useState(""),
    [busy, setBusy] = useState(false);
  const [duplicate, setDuplicate] = useState<RecordData | null>(null),
    [duplicateName, setDuplicateName] = useState(""),
    [testResult, setTestResult] = useState<Job | null>(null);
  const [testPending, setTestPending] = useState<{
      id: number;
      key: string;
    } | null>(null),
    [loading, setLoading] = useState(true);
  const lock = useRef(false);
  async function load() {
    setLoading(true);
    try {
      setRows(await all<RecordData>("/" + entity));
      if (entity === "products") {
        setTemplates(await all<Template>("/templates"));
        setPrinters(await all<Printer>("/printers"));
      }
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }
  useEffect(() => {
    load();
  }, [entity]);
  function edit(row: RecordData) {
    setIdent(row.id!);
    const value: RecordData = {};
    Object.keys(defaults[entity]).forEach((key) => {
      value[key] = row[key] ?? defaults[entity][key];
    });
    if (entity === "users") value.password = "";
    setData(structuredClone(value));
    setError("");
    setMessage("");
    setTestResult(null);
  }
  function fresh() {
    setIdent(null);
    setData(structuredClone(defaults[entity]));
    setError("");
    setMessage("");
  }
  async function save(e: React.FormEvent) {
    e.preventDefault();
    if (lock.current || !data) return;
    lock.current = true;
    setBusy(true);
    setError("");
    try {
      const body = { ...data };
      if (entity === "users" && !body.password) delete body.password;
      const result = ident
        ? await put<RecordData>(`/${entity}/${ident}`, body)
        : await post<RecordData>("/" + entity, body);
      await load();
      edit(result);
      setMessage("Záznam uložen.");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      lock.current = false;
      setBusy(false);
    }
  }
  async function remove(row: RecordData) {
    if (
      !window.confirm(
        `Odstranit ${row.product_code || row.name || row.username}? Historie tisku zůstane zachována.`,
      )
    )
      return;
    setBusy(true);
    setError("");
    try {
      await api(`/${entity}/${row.id}`, { method: "DELETE" });
      if (ident === row.id) {
        setData(null);
        setIdent(null);
      }
      await load();
      setMessage("Záznam odstraněn.");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function duplicateRecord(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const result = await post<RecordData>(
        `/${entity}/${duplicate!.id}/duplicate`,
        { name: duplicateName },
      );
      setDuplicate(null);
      await load();
      edit(result);
      setMessage("Kopie vytvořena.");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function testPrinter(id: number, print: boolean) {
    if (lock.current) return;
    lock.current = true;
    setBusy(true);
    setError("");
    try {
      if (print) {
        const pending = testPending || { id, key: requestToken() };
        setTestPending(pending);
        setTestResult(
          await post<Job>(`/printers/${pending.id}/test-print`, {
            reason: "Printer test",
            idempotency_key: pending.key,
          }),
        );
        setTestPending(null);
      } else {
        const result = await post<{ status: string; error?: string }>(
          `/printers/${id}/test-connection`,
        );
        if (result.status === "failed")
          setError(result.error || "Tiskárna není dostupná");
        else setMessage("TCP spojení funguje. Fyzický tisk tím není potvrzen.");
      }
    } catch (e) {
      setError((e as Error).message);
    } finally {
      lock.current = false;
      setBusy(false);
    }
  }
  const filtered = rows.filter((row) =>
    JSON.stringify([row.product_code, row.name, row.username, row.description])
      .toLocaleLowerCase()
      .includes(search.toLocaleLowerCase()),
  );
  return (
    <>
      <div className="page-heading">
        <div>
          <p className="eyebrow">ADMINISTRACE</p>
          <h1>{names[entity]}</h1>
          <p>
            {entity === "printers"
              ? "Síťové Zebra tiskárny. Adresy smí měnit pouze administrátor."
              : entity === "templates"
                ? "Datové šablony s textem a QR."
                : "Správa záznamů a jejich aktivního stavu."}
          </p>
        </div>
        <button onClick={fresh} disabled={busy}>
          + Nový záznam
        </button>
      </div>
      <ErrorBox error={error} />
      {message && (
        <div className="alert success" role="status">
          {message}
        </div>
      )}
      <div className={"admin-layout " + (data ? "editing" : "")}>
        <section className="card">
          <label>
            Hledat
            <input value={search} onChange={(e) => setSearch(e.target.value)} />
          </label>
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Záznam</th>
                  <th>Stav</th>
                  <th>Akce</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((row) => (
                  <tr key={row.id}>
                    <td>
                      <strong>
                        {String(row.product_code || row.name || row.username)}
                      </strong>
                      <small>
                        {String(
                          row.description || row.host || row.display_name || "",
                        )}
                        {entity === "users"
                          ? " · " +
                            roleNames[row.role as keyof typeof roleNames]
                          : ""}
                      </small>
                    </td>
                    <td>
                      <span
                        className={"badge " + (row.active ? "sent" : "failed")}
                      >
                        {row.active ? "Aktivní" : "Neaktivní"}
                      </span>
                    </td>
                    <td>
                      <div className="row wrap">
                        <button
                          className="secondary small"
                          onClick={() => edit(row)}
                          disabled={busy}
                        >
                          Upravit
                        </button>
                        {(entity === "products" || entity === "templates") && (
                          <button
                            className="secondary small"
                            onClick={() => {
                              setDuplicate(row);
                              setDuplicateName(
                                String(row.product_code || row.name) + " COPY",
                              );
                            }}
                            disabled={busy}
                          >
                            Duplikovat
                          </button>
                        )}
                        <button
                          className="danger small"
                          onClick={() => remove(row)}
                          disabled={busy}
                        >
                          Odstranit
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {!filtered.length && (
            <p className="empty">
              {loading ? "Načítání…" : "Zatím žádné záznamy."}
            </p>
          )}
        </section>
        {data && (
          <section className="card editor-card">
            <div className="row spread">
              <h2>{ident ? "Úprava" : "Nový záznam"}</h2>
              <button
                className="secondary small"
                onClick={() => setData(null)}
                disabled={busy}
              >
                Zavřít
              </button>
            </div>
            <form onSubmit={save}>
              <fieldset disabled={busy} className="fields">
                {fields(entity, templates, printers, !ident).map((field) => (
                  <FieldInput
                    key={field.key}
                    field={field}
                    value={data[field.key]}
                    set={(value) => setData({ ...data, [field.key]: value })}
                  />
                ))}
                {entity === "templates" && (
                  <TemplateEditor data={data} set={setData} />
                )}
              </fieldset>
              <button className="full" disabled={busy}>
                {busy ? "Ukládání…" : "Uložit"}
              </button>
            </form>
            {entity === "products" && !data.template_id && (
              <p className="muted">
                Bez přiřazené šablony produkt nelze tisknout.
              </p>
            )}
            {entity === "printers" && ident && (
              <div className="printer-tests">
                <h3>Ověření tiskárny</h3>
                <p className="muted">
                  Testovací štítek má 60 × 40 mm a vytvoří auditní záznam.
                </p>
                <div className="row wrap">
                  <button
                    className="secondary"
                    onClick={() => testPrinter(ident, false)}
                    disabled={busy || !!testPending}
                  >
                    Test spojení
                  </button>
                  <button
                    className="secondary"
                    onClick={() => testPrinter(ident, true)}
                    disabled={busy}
                  >
                    {testPending
                      ? "Ověřit stejný test"
                      : "Tisk 1 testovacího štítku"}
                  </button>
                </div>
                {testResult && (
                  <JobResult job={testResult} onRefresh={setTestResult} />
                )}
              </div>
            )}
          </section>
        )}
      </div>
      {duplicate && (
        <div className="modal-backdrop">
          <form className="modal" onSubmit={duplicateRecord}>
            <h2>Duplikovat záznam</h2>
            <label>
              Nový kód / název
              <input
                required
                maxLength={120}
                value={duplicateName}
                onChange={(e) => setDuplicateName(e.target.value)}
              />
            </label>
            <ErrorBox error={error} />
            <div className="row">
              <button disabled={busy}>Vytvořit kopii</button>
              <button
                type="button"
                className="secondary"
                onClick={() => setDuplicate(null)}
                disabled={busy}
              >
                Zrušit
              </button>
            </div>
          </form>
        </div>
      )}
    </>
  );
}

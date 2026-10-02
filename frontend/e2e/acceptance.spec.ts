import { test, expect, Page } from "@playwright/test";
import { existsSync, readFileSync } from "node:fs";
import { createHash } from "node:crypto";
import { resolve } from "node:path";

const envFile = process.env.E2E_ENV_FILE || "../.tools/acceptance.env";
const env = Object.fromEntries(
  (existsSync(envFile) ? readFileSync(envFile, "utf8") : "")
    .split(/\r?\n/)
    .filter((s) => s.includes("="))
    .map((s) => [s.slice(0, s.indexOf("=")), s.slice(s.indexOf("=") + 1)]),
);
const password = process.env.E2E_ADMIN_PASSWORD || env.ADMIN_PASSWORD;
if (!password)
  throw new Error(
    "Configure E2E_ENV_FILE or E2E_ADMIN_PASSWORD for the isolated acceptance stack",
  );
const adminUsername =
  process.env.E2E_ADMIN_USERNAME || env.ADMIN_USERNAME || "admin";
const suffix = Date.now().toString();
const productCode = "E2E-" + suffix;
const printerName = "Zebra E2E " + suffix;
const simulator = process.env.E2E_SIMULATOR_URL || "http://127.0.0.1:19191";

async function login(page: Page, username = adminUsername, pwd = password) {
  await page.goto("/");
  await page.getByLabel("Uživatelské jméno").fill(username);
  await page.getByLabel("Heslo", { exact: true }).fill(pwd);
  await page.getByRole("button", { name: "Přihlásit se", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Tisk štítků", exact: true }),
  ).toBeVisible();
}

test.beforeEach(async ({ page }) => {
  await login(page);
});

test("configure templates, network printer and product; send 40 labels; audited reprint", async ({
  page,
  request,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.getByRole("link", { name: "Šablony", exact: true }).click();
  await page
    .getByRole("button", { name: "+ Nový záznam", exact: true })
    .click();
  await page
    .getByLabel("Název šablony", { exact: true })
    .fill("Standard E2E " + suffix);
  await expect(page.getByRole("img", { name: "Náhled štítku" })).toBeVisible();
  await page.getByRole("button", { name: "Uložit", exact: true }).click();
  await expect(page.getByText("Záznam uložen.", { exact: true })).toBeVisible();
  await page.getByRole("link", { name: "Tiskárny", exact: true }).click();
  await page
    .getByRole("button", { name: "+ Nový záznam", exact: true })
    .click();
  await page.getByLabel("Název tiskárny").fill(printerName);
  await page.getByLabel("Hostname / IP").fill("simulator");
  await page.getByLabel("Umístění").fill("Acceptance test");
  await page.getByRole("button", { name: "Uložit", exact: true }).click();
  await expect(page.getByText("Záznam uložen.", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Test spojení", exact: true }).click();
  await expect(
    page.getByText("TCP spojení funguje.", { exact: false }),
  ).toBeVisible();
  await page.getByRole("link", { name: "Produkty", exact: true }).click();
  await page
    .getByRole("button", { name: "+ Nový záznam", exact: true })
    .click();
  await page.getByLabel("Kód produktu", { exact: true }).fill(productCode);
  await page
    .getByLabel("Popis", { exact: true })
    .fill("Ověření dávkového tisku");
  await page
    .getByLabel("Šablona", { exact: true })
    .selectOption({ label: "Standard E2E " + suffix });
  await page
    .getByLabel("Preferovaná tiskárna", { exact: true })
    .selectOption({ label: printerName });
  await page
    .getByLabel("QR obsah", { exact: true })
    .fill("https://erp.local/" + productCode);
  await page.getByLabel("Text 1", { exact: true }).fill("MOTOR SESTAVA Č. 40");
  await page.getByRole("button", { name: "Uložit", exact: true }).click();
  await expect(page.getByText("Záznam uložen.", { exact: true })).toBeVisible();
  await page.getByRole("link", { name: "Tisk štítků", exact: true }).click();
  await page.getByLabel("Vyhledat produkt").fill(productCode);
  await page.getByRole("button", { name: new RegExp(productCode) }).click();
  await page.getByLabel("Množství", { exact: true }).fill("40");
  await page.getByLabel("Důvod", { exact: true }).selectOption("Relabeling");
  await page.getByLabel("Reference", { exact: true }).fill("REF-E2E");
  await expect(
    page.getByRole("button", { name: "TISKNOUT · 40 ks", exact: true }),
  ).toBeEnabled();
  await page.screenshot({
    path: "test-results/print-workflow.png",
    fullPage: true,
  });
  const responsePromise = page.waitForResponse(
    (r) =>
      r.url().endsWith("/api/print-jobs") && r.request().method() === "POST",
  );
  await page
    .getByRole("button", { name: "TISKNOUT · 40 ks", exact: true })
    .dblclick();
  const job = await (await responsePromise).json();
  expect(job.status).toBe("sent");
  expect(job.quantity).toBe(40);
  expect(job.zpl).toContain("^PQ40,0,1,Y");
  await expect(page.locator(".job-result.sent")).toContainText(
    "Odesláno · 40 ks",
  );
  await expect(
    page.getByRole("button", { name: "TISKNOUT · 40 ks", exact: true }),
  ).toBeDisabled();
  await expect
    .poll(
      async () =>
        (await (await request.get(simulator)).json()).filter((zpl: string) =>
          zpl.includes("^PQ40,0,1,Y"),
        ).length,
    )
    .toBeGreaterThan(0);
  await page.getByRole("link", { name: "Historie", exact: true }).click();
  await page.getByLabel("Kód produktu", { exact: true }).fill(productCode);
  await page
    .getByRole("button", { name: "Otevřít", exact: true })
    .first()
    .click();
  await expect(
    page.getByRole("heading", { name: "Detail úlohy" }),
  ).toBeVisible();
  await page.getByLabel("Množství", { exact: true }).fill("3");
  await page
    .getByRole("button", { name: "Opakovat tisk · 3 ks", exact: true })
    .click();
  await expect(page.locator(".modal .job-result.sent").last()).toContainText(
    "Odesláno · 3 ks",
  );
  await page.getByRole("button", { name: "Zavřít", exact: true }).click();
  await expect(page.locator("tbody tr")).toHaveCount(2);
  expect(errors).toEqual([]);
});

test("user administration and viewer permissions", async ({ page }) => {
  const username = "viewer-" + suffix;
  await page.getByRole("link", { name: "Uživatelé", exact: true }).click();
  await page
    .getByRole("button", { name: "+ Nový záznam", exact: true })
    .click();
  await page.getByLabel("Uživatelské jméno", { exact: true }).fill(username);
  await page
    .getByLabel("Heslo (min. 12 znaků)", { exact: true })
    .fill("viewer-password-123");
  await page.getByLabel("Role", { exact: true }).selectOption("viewer");
  await page.getByRole("button", { name: "Uložit", exact: true }).click();
  await expect(page.getByText("Záznam uložen.", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Odhlásit se", exact: true }).click();
  await login(page, username, "viewer-password-123");
  await expect(
    page.getByRole("link", { name: "Uživatelé", exact: true }),
  ).toHaveCount(0);
  await expect(page.getByRole("button", { name: /TISKNOUT/ })).toBeDisabled();
  const me = await (await page.request.get("/api/auth/me")).json();
  const denied = await page.request.post("/api/printers", {
    headers: { "X-CSRF-Token": me.csrf_token },
    data: { name: "forbidden", host: "127.0.0.1" },
  });
  expect(denied.status()).toBe(403);
  await page.getByRole("link", { name: "Historie", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Historie tisku", exact: true }),
  ).toBeVisible();
});

test("upload SQLite copy, inspect dry-run, execute import and preserve source", async ({
  page,
}) => {
  const path = resolve("e2e/fixtures/legacy-copy.db");
  const digest = () =>
    createHash("sha256").update(readFileSync(path)).digest("hex");
  const before = digest();
  await page
    .getByRole("link", { name: "Import katalogu", exact: true })
    .click();
  await page
    .getByLabel("Kopie SQLite databáze", { exact: false })
    .setInputFiles(path);
  await page.getByLabel("Potvrzuji, že nahrávám", { exact: false }).check();
  await page
    .getByRole("button", { name: "Spustit dry-run", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Výsledek dry-run", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText("SHA-256 kopie: " + before, { exact: true }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Potvrdit a provést import", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Import dokončen", exact: true }),
  ).toBeVisible();
  expect(digest()).toBe(before);
  const products = await (
    await page.request.get("/api/products?q=IMPORTED-001")
  ).json();
  expect(products[0].text4).toBe("text4");
  expect(products[0].highlight_right).toBe(true);
  const template = await (
    await page.request.get("/api/templates/" + products[0].template_id)
  ).json();
  expect(template.name).toBe("Imported standard");
});

test("network failure is visible and audit history retains failed attempt", async ({
  page,
}) => {
  const me = await (await page.request.get("/api/auth/me")).json();
  const printer = await (
    await page.request.post("/api/printers", {
      headers: { "X-CSRF-Token": me.csrf_token },
      data: { name: "Offline " + suffix, host: "127.0.0.1", port: 9199 },
    })
  ).json();
  await page.reload();
  await page.getByLabel("Vyhledat produkt").fill("IMPORTED-001");
  await page.getByRole("button", { name: /IMPORTED-001/ }).click();
  await page
    .getByLabel("Tiskárna", { exact: true })
    .selectOption(String(printer.id));
  await page.getByLabel("Množství", { exact: true }).fill("4");
  await expect(
    page.getByRole("button", { name: "TISKNOUT · 4 ks", exact: true }),
  ).toBeEnabled();
  await page
    .getByRole("button", { name: "TISKNOUT · 4 ks", exact: true })
    .click();
  await expect(page.locator(".job-result.failed")).toContainText(
    "ConnectionRefusedError",
  );
  await page.getByRole("link", { name: "Historie", exact: true }).click();
  await page.getByLabel("Stav", { exact: true }).selectOption("failed");
  await expect(page.locator("tbody")).toContainText("IMPORTED-001");
});

test("lost HTTP response retries the same token without a second TCP send", async ({
  page,
  request,
}) => {
  const printers = await (await page.request.get("/api/printers")).json();
  const printer = printers.find(
    (p: { host: string }) => p.host === "simulator",
  );
  await page.getByLabel("Vyhledat produkt").fill("IMPORTED-001");
  await page.getByRole("button", { name: /IMPORTED-001/ }).click();
  await page
    .getByLabel("Tiskárna", { exact: true })
    .selectOption(String(printer.id));
  await page.getByLabel("Množství", { exact: true }).fill("7");
  const before = (await (await request.get(simulator)).json()).length;
  let interrupted = false;
  await page.route("**/api/print-jobs", async (route) => {
    if (!interrupted && route.request().method() === "POST") {
      interrupted = true;
      await route.fetch();
      await route.abort("failed");
    } else await route.continue();
  });
  await expect(
    page.getByRole("button", { name: "TISKNOUT · 7 ks", exact: true }),
  ).toBeEnabled();
  await page
    .getByRole("button", { name: "TISKNOUT · 7 ks", exact: true })
    .click();
  await expect(
    page.getByRole("button", { name: "Ověřit stejný požadavek", exact: true }),
  ).toBeEnabled();
  await page.reload();
  await expect(
    page.getByRole("button", { name: "Ověřit stejný požadavek", exact: true }),
  ).toBeEnabled();
  await page
    .getByRole("button", { name: "Ověřit stejný požadavek", exact: true })
    .click();
  await expect(page.locator(".job-result.sent")).toContainText(
    "Odesláno · 7 ks",
  );
  await expect
    .poll(async () => (await (await request.get(simulator)).json()).length)
    .toBe(before + 1);
});

test("responsive operational screen remains usable", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.getByLabel("Vyhledat produkt").fill("IMPORTED-001");
  await page.getByRole("button", { name: /IMPORTED-001/ }).click();
  const printers = await (await page.request.get("/api/printers")).json();
  await page
    .getByLabel("Tiskárna", { exact: true })
    .selectOption(
      String(printers.find((p: { host: string }) => p.host === "simulator").id),
    );
  await expect(page.getByRole("img", { name: "Náhled štítku" })).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
  await page.screenshot({
    path: "test-results/print-mobile.png",
    fullPage: true,
  });
});

test("settings update changes defaults and backend limits", async ({
  page,
}) => {
  const original = await (await page.request.get("/api/settings")).json();
  await page.getByRole("link", { name: "Nastavení", exact: true }).click();
  await page.getByLabel("Výchozí množství", { exact: true }).fill("2");
  await page.getByLabel("Maximální množství", { exact: true }).fill("20");
  await page
    .getByRole("button", { name: "Uložit nastavení", exact: true })
    .click();
  await expect(
    page.getByText("Nastavení uloženo.", { exact: true }),
  ).toBeVisible();
  await page.getByRole("link", { name: "Tisk štítků", exact: true }).click();
  await expect(page.getByLabel("Množství", { exact: true })).toHaveValue("2");
  await expect(page.getByLabel("Množství", { exact: true })).toHaveAttribute(
    "max",
    "20",
  );
  const me = await (await page.request.get("/api/auth/me")).json();
  const products = await (
    await page.request.get("/api/products?q=IMPORTED-001")
  ).json();
  const printers = await (await page.request.get("/api/printers")).json();
  const rejected = await (
    await page.request.post("/api/print-jobs", {
      headers: { "X-CSRF-Token": me.csrf_token },
      data: {
        product_id: products[0].id,
        printer_id: printers.find(
          (p: { host: string }) => p.host === "simulator",
        ).id,
        quantity: 21,
        reason: original.reasons[0],
        idempotency_key: "settings-limit-" + Date.now(),
      },
    })
  ).json();
  expect(rejected.status).toBe("failed");
  expect(rejected.error).toContain("maximum 20");
  await page.getByRole("link", { name: "Nastavení", exact: true }).click();
  await page
    .getByLabel("Maximální množství", { exact: true })
    .fill(String(original.max_quantity));
  await page
    .getByLabel("Výchozí množství", { exact: true })
    .fill(String(original.default_quantity));
  await page
    .getByRole("button", { name: "Uložit nastavení", exact: true })
    .click();
  await expect(
    page.getByText("Nastavení uloženo.", { exact: true }),
  ).toBeVisible();
});

test("uncertain reprint survives closing and reload without sending twice", async ({
  page,
  request,
}) => {
  await page.getByRole("link", { name: "Historie", exact: true }).click();
  await page.getByLabel("Kód produktu", { exact: true }).fill("IMPORTED-001");
  await page.getByLabel("Stav", { exact: true }).selectOption("sent");
  await page
    .getByRole("button", { name: "Otevřít", exact: true })
    .first()
    .click();
  await page.getByLabel("Množství", { exact: true }).fill("2");
  const before = (await (await request.get(simulator)).json()).length;
  let interrupted = false;
  await page.route("**/api/print-jobs/*/reprint", async (route) => {
    if (!interrupted) {
      interrupted = true;
      await route.fetch();
      await route.abort("failed");
    } else await route.continue();
  });
  await page
    .getByRole("button", { name: "Opakovat tisk · 2 ks", exact: true })
    .click();
  await expect(
    page.getByRole("button", { name: "Ověřit stejný požadavek", exact: true }),
  ).toBeEnabled();
  await page.getByRole("button", { name: "Zavřít", exact: true }).click();
  await page.reload();
  await page.getByLabel("Kód produktu", { exact: true }).fill("IMPORTED-001");
  await page.getByLabel("Stav", { exact: true }).selectOption("sent");
  await expect(page.locator("tbody tr").first()).toContainText("IMPORTED-001");
  await page
    .getByRole("button", { name: "Otevřít", exact: true })
    .nth(1)
    .click();
  await expect(
    page.getByRole("button", { name: "Ověřit stejný požadavek", exact: true }),
  ).toBeEnabled();
  await page
    .getByRole("button", { name: "Ověřit stejný požadavek", exact: true })
    .click();
  await expect(page.locator(".modal .job-result.sent").last()).toContainText(
    "Odesláno · 2 ks",
  );
  await expect
    .poll(async () => (await (await request.get(simulator)).json()).length)
    .toBe(before + 1);
});

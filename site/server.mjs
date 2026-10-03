import { createServer } from "node:http";
import { readFile, stat } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const publicDir = path.join(here, "public");
const port = Number(process.env.PORT || 3000);
const host = process.env.HOST || "127.0.0.1";
const maxBody = 8192;
const rateWindow = 15 * 60 * 1000;
const rateLimit = 20;
const requests = new Map();

const telegramReady = () => Boolean(process.env.TELEGRAM_BOT_TOKEN && process.env.TELEGRAM_CHAT_ID);
const maxReady = () => Boolean(process.env.MAX_BOT_TOKEN && process.env.MAX_CHAT_ID);
const ready = () => telegramReady() || maxReady();

function json(res, status, body) {
  res.writeHead(status, {
    "Content-Type": "application/json; charset=utf-8",
    "Cache-Control": "no-store",
    "X-Content-Type-Options": "nosniff",
  });
  res.end(JSON.stringify(body));
}

function clean(value, max) {
  return typeof value === "string" ? value.trim().slice(0, max) : "";
}

function number(value) {
  return typeof value === "string" || typeof value === "number" ? Number(value) : NaN;
}

function validate(raw) {
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) return null;
  if (clean(raw.website, 120)) return { spam: true };
  const lead = {
    product: clean(raw.product, 120),
    quantity: number(raw.quantity),
    weightGrams: number(raw.weightGrams),
    fulfillmentScheme: raw.fulfillmentScheme,
    plannedMonthlyVolume: number(raw.plannedMonthlyVolume),
    averageShipmentsPerDay: raw.averageShipmentsPerDay === undefined || raw.averageShipmentsPerDay === null || raw.averageShipmentsPerDay === ""
      ? undefined
      : number(raw.averageShipmentsPerDay),
    lengthCm: number(raw.lengthCm),
    widthCm: number(raw.widthCm),
    heightCm: number(raw.heightCm),
    honestSign: raw.honestSign,
    preparationLevel: raw.preparationLevel,
    contactName: clean(raw.contactName, 80),
    phone: clean(raw.phone, 25),
    contactMethod: raw.contactMethod,
    contactHandle: clean(raw.contactHandle, 80),
    comment: clean(raw.comment, 700),
    consent: raw.consent === true,
  };
  const bounded = (value, min, max) => Number.isFinite(value) && value >= min && value <= max;
  const digits = lead.phone.replace(/\D/g, "");
  const valid = lead.product && lead.contactName && digits.length >= 7 && digits.length <= 15 &&
    bounded(lead.quantity, 1, 10_000_000) && bounded(lead.weightGrams, 1, 100_000) &&
    ["FBO", "FBS"].includes(lead.fulfillmentScheme) &&
    bounded(lead.plannedMonthlyVolume, 1, 10_000_000) &&
    (lead.fulfillmentScheme === "FBO" || bounded(lead.averageShipmentsPerDay, 0, 100_000)) &&
    bounded(lead.lengthCm, 0.1, 5_000) && bounded(lead.widthCm, 0.1, 5_000) &&
    bounded(lead.heightCm, 0.1, 5_000) && ["Да", "Нет", "Не знаю"].includes(lead.honestSign) &&
    ["Упаковка и маркировка", "Только маркировка", "Уже упакован и промаркирован"].includes(lead.preparationLevel) &&
    ["Звонок по телефону", "Telegram", "MAX"].includes(lead.contactMethod) && lead.consent;
  return valid ? { lead } : null;
}

function formatLead(lead) {
  return [
    "Новая заявка с сайта PORTAL", "",
    `Товар: ${lead.product}`,
    `Количество: ${lead.quantity} шт.`,
    `Средний вес 1 ед.: ${lead.weightGrams} г`,
    `Схема: ${lead.fulfillmentScheme}`,
    `Планируемый объём в месяц: ${lead.plannedMonthlyVolume} шт.`,
    lead.fulfillmentScheme === "FBS" ? `Среднее количество отгрузок в день: ${lead.averageShipmentsPerDay}` : "",
    `Размер 1 ед.: ${lead.lengthCm} × ${lead.widthCm} × ${lead.heightCm} см`,
    `«Честный знак»: ${lead.honestSign}`, "",
    `Подготовка товара: ${lead.preparationLevel}`,
    `Клиент: ${lead.contactName}`,
    `Телефон: ${lead.phone}`,
    `Связаться: ${lead.contactMethod}`,
    lead.contactHandle ? `Контакт в мессенджере: ${lead.contactHandle}` : "",
    lead.comment ? `Комментарий: ${lead.comment}` : "",
  ].filter(Boolean).join("\n").slice(0, 3900);
}

async function sendTelegram(text) {
  const response = await fetch(`https://api.telegram.org/bot${process.env.TELEGRAM_BOT_TOKEN}/sendMessage`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ chat_id: process.env.TELEGRAM_CHAT_ID, text, disable_web_page_preview: true }),
    signal: AbortSignal.timeout(8000),
  });
  const result = await response.json().catch(() => ({}));
  if (!response.ok || !result.ok) throw new Error("telegram_delivery_failed");
}

async function sendMax(text) {
  const response = await fetch(`https://platform-api2.max.ru/messages?chat_id=${encodeURIComponent(process.env.MAX_CHAT_ID)}`, {
    method: "POST",
    headers: { Authorization: process.env.MAX_BOT_TOKEN, "Content-Type": "application/json" },
    body: JSON.stringify({ text, notify: true }),
    signal: AbortSignal.timeout(8000),
  });
  if (!response.ok) throw new Error("max_delivery_failed");
}

function originAllowed(req) {
  const origin = req.headers.origin;
  if (!origin) return false;
  const expected = process.env.PUBLIC_ORIGIN;
  if (expected) return origin === expected.replace(/\/$/, "");
  try { return new URL(origin).host === req.headers.host; } catch { return false; }
}

function allowedByRateLimit(req) {
  const forwarded = String(req.headers["x-real-ip"] || "");
  const key = forwarded || req.socket.remoteAddress || "unknown";
  const now = Date.now();
  const recent = (requests.get(key) || []).filter((time) => now - time < rateWindow);
  if (recent.length >= rateLimit) { requests.set(key, recent); return false; }
  recent.push(now);
  requests.set(key, recent);
  return true;
}

async function readJson(req) {
  const chunks = [];
  let size = 0;
  for await (const chunk of req) {
    size += chunk.length;
    if (size > maxBody) throw Object.assign(new Error("too_large"), { status: 413 });
    chunks.push(chunk);
  }
  try { return JSON.parse(Buffer.concat(chunks).toString("utf8")); }
  catch { throw Object.assign(new Error("invalid"), { status: 400 }); }
}

const mime = {
  ".css": "text/css; charset=utf-8", ".html": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8", ".json": "application/json; charset=utf-8",
  ".png": "image/png", ".svg": "image/svg+xml", ".webp": "image/webp",
  ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".ico": "image/x-icon",
};

async function serveStatic(req, res, pathname) {
  let requested;
  try { requested = pathname === "/" ? "/index.html" : decodeURIComponent(pathname); }
  catch { return json(res, 400, { code: "invalid_path" }); }
  const file = path.resolve(publicDir, `.${requested}`);
  if (!file.startsWith(`${publicDir}${path.sep}`)) return json(res, 404, { code: "not_found" });
  try {
    if (!(await stat(file)).isFile()) return json(res, 404, { code: "not_found" });
    const body = await readFile(file);
    res.writeHead(200, {
      "Content-Type": mime[path.extname(file).toLowerCase()] || "application/octet-stream",
      "Cache-Control": path.extname(file) === ".html" ? "no-cache" : "public, max-age=3600",
      "X-Content-Type-Options": "nosniff",
      "Referrer-Policy": "strict-origin-when-cross-origin",
      "X-Frame-Options": "DENY",
    });
    res.end(req.method === "HEAD" ? undefined : body);
  } catch { json(res, 404, { code: "not_found" }); }
}

async function handleRequest(req, res) {
  let url;
  try { url = new URL(req.url || "/", `http://${req.headers.host || "localhost"}`); }
  catch { return json(res, 400, { code: "invalid_url" }); }
  if (url.pathname === "/api/leads") {
    if (req.method === "GET") return json(res, 200, { configured: ready() });
    if (req.method !== "POST") return json(res, 405, { code: "method_not_allowed" });
    if (!originAllowed(req)) return json(res, 403, { code: "forbidden" });
    if (!String(req.headers["content-type"] || "").toLowerCase().includes("application/json")) return json(res, 415, { code: "invalid" });
    if (!allowedByRateLimit(req)) return json(res, 429, { code: "rate_limited" });
    let raw;
    try { raw = await readJson(req); }
    catch (error) { return json(res, error.status || 400, { code: error.message || "invalid" }); }
    const result = validate(raw);
    if (!result) return json(res, 400, { code: "invalid" });
    if (result.spam) return json(res, 200, { ok: true });
    if (!ready()) return json(res, 503, { code: "setup_pending" });
    const message = formatLead(result.lead);
    const tasks = [
      ...(telegramReady() ? [sendTelegram(message)] : []),
      ...(maxReady() ? [sendMax(message)] : []),
    ];
    const results = await Promise.allSettled(tasks);
    const delivered = results.filter((item) => item.status === "fulfilled").length;
    if (delivered === tasks.length) return json(res, 200, { ok: true });
    if (delivered > 0) return json(res, 502, { code: "partial_delivery" });
    return json(res, 502, { code: "delivery_failed" });
  }
  if (req.method !== "GET" && req.method !== "HEAD") return json(res, 405, { code: "method_not_allowed" });
  await serveStatic(req, res, url.pathname);
}

const server = createServer((req, res) => {
  handleRequest(req, res).catch(() => {
    if (res.headersSent) { res.destroy(); return; }
    try { json(res, 500, { code: "internal_error" }); }
    catch { res.destroy(); }
  });
});

server.listen(port, host, () => console.log(`PORTAL site listening on http://${host}:${port}`));

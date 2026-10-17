import { test } from "node:test";
import assert from "node:assert/strict";
import { mkdtemp, readFile, rm } from "node:fs/promises";
import path from "node:path";
import { tmpdir } from "node:os";
import { persistLead, storagePath, hasLeadStorage } from "./lead_inbox.mjs";

test("private lead inbox requires explicit storage outside website assets", async () => {
  const original = process.env.PORTAL_SITE_LEADS_FILE;
  const dir = await mkdtemp(path.join(tmpdir(), "portal-lead-inbox-"));
  try {
    const web = path.join(dir, "public");
    delete process.env.PORTAL_SITE_LEADS_FILE;
    assert.equal(hasLeadStorage(web), false);
    await assert.rejects(persistLead({ contactName: "TEST" }, web));
    process.env.PORTAL_SITE_LEADS_FILE = path.join(web, "exposed.jsonl");
    assert.equal(storagePath(web), null);
    process.env.PORTAL_SITE_LEADS_FILE = path.join(dir, "private", "leads.jsonl");
    assert.equal(hasLeadStorage(web), true);
    const id = await persistLead({ product: "Synthetic item", contactName: "TEST" }, web);
    assert.match(id, /^[0-9a-f-]{36}$/);
    const rows = (await readFile(process.env.PORTAL_SITE_LEADS_FILE, "utf8")).trim().split("\n").map(JSON.parse);
    assert.equal(rows.length, 1);
    assert.equal(rows[0].id, id);
    assert.equal(rows[0].lead.contactName, "TEST");
    assert.match(rows[0].received_at, /^\d{4}-\d\d-\d\dT/);
  } finally {
    if (original === undefined) delete process.env.PORTAL_SITE_LEADS_FILE;
    else process.env.PORTAL_SITE_LEADS_FILE = original;
    await rm(dir, { recursive: true, force: true });
  }
});

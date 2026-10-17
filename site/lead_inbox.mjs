import { constants } from "node:fs";
import { mkdir, open } from "node:fs/promises";
import { randomUUID } from "node:crypto";
import path from "node:path";

// Configure a persistent absolute path outside public assets, e.g.
// /var/lib/portal-site/leads.jsonl. Without storage: fail closed (503).
export function storagePath(publicDir) {
  const raw = process.env.PORTAL_SITE_LEADS_FILE || "";
  if (!path.isAbsolute(raw)) return null;
  const resolved = path.resolve(raw);
  const publicRoot = path.resolve(publicDir);
  if (resolved === publicRoot || resolved.startsWith(publicRoot + path.sep)) return null;
  return resolved;
}

export function hasLeadStorage(publicDir) {
  return storagePath(publicDir) !== null;
}

export async function persistLead(lead, publicDir) {
  const filename = storagePath(publicDir);
  if (!filename) throw new Error("private lead storage not configured");
  const dir = path.dirname(filename);
  await mkdir(dir, { recursive: true, mode: 0o700 });
  // O_NOFOLLOW protects against a symlink replacing the target file.
  const flags = constants.O_WRONLY | constants.O_APPEND | constants.O_CREAT | (constants.O_NOFOLLOW || 0);
  const file = await open(filename, flags, 0o600);
  try {
    const info = await file.stat();
    if (!info.isFile() || info.nlink !== 1) throw new Error("invalid private lead file");
    const record = {
      id: randomUUID(),
      received_at: new Date().toISOString(),
      lead,
    };
    const message = Buffer.from(JSON.stringify(record) + "\n", "utf8");
    const { bytesWritten } = await file.write(message, 0, message.length);
    if (bytesWritten !== message.length) throw new Error("lead write incomplete");
    await file.sync();
    return record.id;
  } finally {
    await file.close();
  }
}

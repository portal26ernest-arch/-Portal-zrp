# PORTAL Server Discovery

## Purpose

PORTAL clients must be able to recover the current official server address even when the previously saved VPS address is no longer reachable and even when no new application release exists.

The stable discovery source is:

`https://raw.githubusercontent.com/portal26ernest-arch/-Portal-zrp/main/portal-server.json`

This GitHub URL is independent from the PORTAL VPS. The user action “Проверить обновления / Обновить PORTAL” checks this document before checking the application version.

## Contract

`portal-server.json` contains:

- `schemaVersion` — discovery schema, currently 1.
- `revision` — monotonically increasing integer. Never decrease or reuse an older revision after a server-address change.
- `apiUrl` — canonical HTTPS PORTAL API origin, without paths, query, fragment, credentials or non-standard port.
- `updatedAt` — ISO-8601 UTC timestamp.

Clients reject malformed documents and rollback to an older revision.

## Safe switch

A client does not trust the URL blindly. Before switching it:

1. downloads the exact discovery document over HTTPS from the pinned GitHub repository path;
2. validates schema, revision and URL shape;
3. probes the candidate `/api/ping` without sending user credentials and requires `ok=true` plus a `PORTAL Server` build marker;
4. migrates pending encrypted local outbox records to the new origin so unsent work is not stranded;
5. only then stores the new server address.

Desktop additionally requires the candidate `/web/` endpoint to answer successfully before switching.

If discovery or probe fails, the current saved address remains unchanged. Application update checking continues independently through the official GitHub Release channel.

## Changing the PORTAL server

When the official production address changes:

1. deploy the new server and complete API/Web smoke first;
2. edit only `portal-server.json` in a fresh branch based on current `main`;
3. increment `revision`;
4. set the new HTTPS `apiUrl` and current `updatedAt`;
5. run CI/review and merge to `main`;
6. do not need to publish a new Android/Desktop/iOS release solely for the address change;
7. users can press “Обновить PORTAL / Проверить обновления”; the client reads the new address from GitHub and switches automatically after validation.

Production runtime must never be moved first and discovery updated later if doing so would strand all existing clients. Keep the old endpoint available during the transition whenever possible.

## Security rule

`portal-server.json` is control-plane configuration. Changes to it follow the same strict GitHub process as code: fresh `main` → branch → review/tests → commit/push → CI → merge. Direct ad-hoc edits on VPS or user devices are not the source of truth.

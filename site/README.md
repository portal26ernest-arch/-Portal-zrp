# PORTAL site backend security candidate

Source reconciled from `/opt/portal-site/server.mjs` on 2026-10-03 (site Git HEAD 92598a080c86304359ae07b3545faf48fc4941a0). Public website assets and deployment environment remain in the site deployment repository. No `.env` or user data is included.

This backend snapshot is versioned in the canonical PORTAL repository so the reviewed security patch has a fixed provenance. Do not deploy from this branch. Integrate into the canonical release line and the site repository, retaining the site's public directory, before activation.

Run `node --test site/server-security.test.mjs` using an isolated temporary listener and synthetic static content. The test removes delivery credentials from the child environment and never contacts production or messaging providers.

## Standalone private lead inbox (candidate, not deployed)

The website backend no longer calls external chat providers. Configure an absolute persistent `PORTAL_SITE_LEADS_FILE` (for example `/var/lib/portal-site/leads.jsonl`) outside the public static directory. Requests return HTTP 200 **only after** the validated lead is appended and synced to a private file (mode 0600); unset or invalid storage fails closed with HTTP 503. The owner/operator must arrange private access to this inbox, backups and retention before any live deployment; removing an old notification channel without this setup would interrupt lead handling.

The separately deployed site public form must be reviewed and updated to remove retired provider options, using a supported contact method. The canonical repository includes only this backend snapshot, not the public assets. Never expose the lead file via nginx, static files, logs or Git. `node --test site/server-security.test.mjs site/lead-inbox.test.mjs` exercises isolated, synthetic leads.

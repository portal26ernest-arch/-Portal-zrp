# PORTAL site backend security candidate

Source reconciled from `/opt/portal-site/server.mjs` on 2026-10-03 (site Git HEAD 92598a080c86304359ae07b3545faf48fc4941a0). Public website assets and deployment environment remain in the site deployment repository. No `.env` or user data is included.

This backend snapshot is versioned in the canonical PORTAL repository so the reviewed security patch has a fixed provenance. Do not deploy from this branch. Integrate into the canonical release line and the site repository, retaining the site's public directory, before activation.

Run `node --test site/server-security.test.mjs` using an isolated temporary listener and synthetic static content. The test removes delivery credentials from the child environment and never contacts production or messaging providers.

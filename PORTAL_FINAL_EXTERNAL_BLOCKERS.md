# PORTAL final external blockers

This list contains owner/provider actions that cannot be established or authorized by repository changes.

| External action | Why it remains external | Owner action required |
|---|---|---|
| Approve and provide the production domain/DNS and network path | Stage 7 report records that the temporary HTTPS path is not a permanent domain and HTTP-01 on TCP/80 did not complete. No DNS or firewall changes were made. | Yes |
| Configure/verify protected production release and service secrets, then explicitly approve release/cutover | Production secrets are intentionally not inspected or printed; Part 12 does not authorize production release/import/cutover. | Yes |
| Perform ordinary user validation on a physical Android device using the CI APK | System picker, installer, and real device display behavior require the owner's device; this is a manual usability check, not an automated build gate. | Yes |
| Supply an official, stable, publicly accessible Ozon/Wildberries news feed or API, if one is available | Repository/configuration contains no proven official public feed; private auth and scraping are out of scope. | Yes (only if a source exists) |
| Supply official TalAnt API documentation, sandbox, and authorized credentials | TalAnt integration is an external API boundary and excluded from Part 12 implementation without provider access. | Yes |
| Select/provision an approved off-server backup provider and credentials | No configured secondary target is evidenced in the repository; a generic backup mechanism cannot prove an external copy exists. | Yes |
| Provide a Windows code-signing certificate if a trusted production installer is required | No Windows signing identity or Windows installer toolchain is evidenced in this checkout. | Yes, for signed distribution |

Production cutover has **not** been performed.

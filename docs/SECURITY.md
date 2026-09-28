# Security and privacy

## Demo data policy

- Use fictional or explicitly consented, de-identified stories.
- Do not request names, phone numbers, school records or identity documents.
- Applicant submissions use random references rather than identity fields.
- Delete pilot submissions after their agreed review window.
- Never commit `.env`, API keys, server credentials, SQLite files or media.

## Implemented controls

- exact content-type and 30 MB limits for media;
- HTTPS links only for external video;
- fixed server-side media paths derived from generated IDs;
- no-store response headers;
- append-only decision events;
- explicit pilot consent;
- optional Basic Auth for closed demonstrations;
- no user-response extraction cache;
- automatic abstention/manual-review routes.

## Before institutional use

Replace demo authentication with separate applicant, reviewer and admin roles;
add malware scanning, encryption and key management, retention jobs, access
audit, backups, incident response, legal approval and an applicant review or
appeal process. Run a threat model and penetration test against the deployed
environment.

Report security issues privately to the repository owners. Do not open a public
issue containing credentials or applicant material.

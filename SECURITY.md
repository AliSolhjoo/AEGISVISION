# Security Policy

AEGISVISION handles authentication data, organization records, network-camera connection details, and potentially sensitive video footage. Treat deployments and test data accordingly.

## Reporting a vulnerability

Please do not publish camera credentials, private video frames, database files, access tokens, or an exploitable vulnerability in a public issue.

If GitHub private vulnerability reporting is enabled for this repository, use the **Security → Advisories → Report a vulnerability** flow. Otherwise, contact the repository maintainer through a verified private contact channel. Include:

- A concise description and potential impact.
- Affected commit, release, or version.
- Safe reproduction steps or a minimal proof of concept.
- Any suggested mitigation, if known.

Do not attach real camera footage, production database dumps, passwords, or live RTSP URLs. Use synthetic examples.

## Deployment requirements

- Never deploy with `DJANGO_DEBUG=True`.
- Set unique `DJANGO_SECRET_KEY` and `JWT_SIGNING_KEY` values outside source control.
- Set explicit `DJANGO_ALLOWED_HOSTS`, `CORS_ALLOWED_ORIGINS`, and `CSRF_TRUSTED_ORIGINS` values.
- Use HTTPS, secure cookies, a properly configured reverse proxy, firewall rules, and least-privilege database credentials.
- Keep `.env`, production databases, backups, camera credentials, videos, frames, logs, and model weights out of public Git history.
- Restrict RTSP/RTSPS access to authorized networks and accounts. Do not expose camera services directly to the public internet.
- Review data-retention, consent, privacy, and access-control requirements before processing camera footage.
- Keep Python and npm dependencies updated and review security advisories before upgrading.

## Camera credential encryption

AEGISVISION encrypts camera usernames and passwords before database storage. The encryption key is derived from Django's `SECRET_KEY`. Keep that secret stable, private, and backed up. Rotating it without first decrypting and re-encrypting stored camera credentials will make existing credentials unreadable.

## Scope and limitations

This policy covers the code in this repository. It is not a guarantee that every deployment is secure by default. Operators are responsible for deployment hardening, network isolation, lawful camera use, secure storage, backups, and timely updates.

# Security Policy

## Reporting a vulnerability

Do not publish camera credentials, private video frames, database files, access tokens, or an exploitable vulnerability in a public issue. Contact the repository maintainer privately through a verified contact channel and include a concise description, impact, affected version, and safe reproduction steps.

## Deployment requirements

- Never deploy with `DJANGO_DEBUG=True`.
- Set unique `DJANGO_SECRET_KEY` and `JWT_SIGNING_KEY` values outside source control.
- Set explicit `DJANGO_ALLOWED_HOSTS`, `CORS_ALLOWED_ORIGINS`, and `CSRF_TRUSTED_ORIGINS` values.
- Use HTTPS, secure cookies, a properly configured reverse proxy, firewall rules, and least-privilege database credentials.
- Keep `.env`, production databases, backups, camera credentials, videos, frames, logs, and model weights out of public Git history.
- Limit RTSP/RTSPS access to authorized networks and accounts.
- Review data-retention, consent, privacy, and access-control requirements before processing camera footage.

## Camera credential encryption

AEGISVISION derives its camera-credential encryption key from Django's `SECRET_KEY`. Keep that secret stable and backed up. Rotating it without decrypting and re-encrypting stored camera credentials will make existing credentials unreadable.

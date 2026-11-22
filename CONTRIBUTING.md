# Contributing to AEGISVISION

Thank you for considering a contribution.

## Before you start

- Read [README.md](README.md) for setup, architecture, supported workflows, and known limitations.
- Read [SECURITY.md](SECURITY.md) before working with camera credentials, authentication, uploads, or deployment settings.
- Check existing issues and pull requests before opening a new one.
- Do not include real camera URLs, credentials, private footage, database files, logs, model weights, or environment files in issues or pull requests.

## Development setup

1. Fork the repository and create a feature branch from `main`.
2. Follow the local setup instructions in README.md.
3. Keep secrets in an untracked root `.env` file. Never commit it.
4. Make the smallest focused change that solves the problem.

## Validation

Run the checks relevant to your change before opening a pull request.

Backend:

```bash
cd backend
python manage.py check
python manage.py test
```

Frontend:

```bash
cd frontend
npm ci
npm run typecheck
npm run build
```

The GitHub Actions workflow runs the frontend type-check/build and a Python syntax compilation check. It does not replace Django integration tests, RTSP hardware tests, CUDA validation, or performance testing.

## Pull request expectations

- Explain the problem and the approach.
- List the main files or modules changed.
- Include test commands and their results.
- Add screenshots for visible UI changes, using synthetic/demo data only.
- Update English and Persian documentation when behavior or setup changes.
- Document new environment variables in `.env.example` with safe placeholders only.
- Add or update tests for bug fixes and new behavior.
- Avoid unrelated formatting or refactoring in focused pull requests.

## Security-sensitive changes

Changes involving authentication, organization permissions, camera credential encryption, upload handling, or network access should include tests for both allowed and denied cases. Never weaken authorization or expose internal camera URLs, tokens, or secrets in API responses, exceptions, logs, or screenshots.

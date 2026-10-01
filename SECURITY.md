# Security

## Reporting a vulnerability

Please do not open a public issue for a security problem. Use GitHub's private reporting instead:
**Security → Report a vulnerability** on this repository.

Include what you found, how to reproduce it, and what an attacker could do with it. You should get a
reply within a week.

## What counts

- Anything that exposes an API key, or lets one client read another's submitted text.
- A way for the extension to act on a page without the user invoking it.
- A way to make the API return model output that was not validated against the submission.

## Known and documented, not vulnerabilities

- **Prompt injection.** Text written to manipulate the analyzer can still move a result. This is an
  open problem, described in [docs/threat-model.md](docs/threat-model.md#1-prompt-injection).
  Reports of new techniques are welcome as regular issues.
- **No rate limiting or spend cap yet.** The API is meant to run locally with your own key until
  those exist (build step 18). Do not expose it to the internet.

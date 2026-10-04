# Security policy

## Sensitive data

Never commit, display, copy into artifacts, or transmit:

- API keys, access tokens, passwords, or private keys;
- `.env` or `.env.*` contents;
- browser profiles or operating-system credential stores;
- authorization headers, cookies, private prompts, or private documents.

Use environment-variable names and placeholders in documentation. Provider
adapters and benchmark runners must obtain credentials from the process
environment. Research provenance must not record the full environment.

If a credential is exposed, revoke or rotate it immediately. Removing the file
from the latest commit does not remove it from Git history.

## Supported deployment posture

The repository is designed for local research and demonstration. The FastAPI
service does not currently implement authentication. Do not expose it directly
to an untrusted network. Bind to loopback unless an authenticated reverse proxy,
network policy, rate limits, and deployment-specific review are added.

## Trust and execution boundaries

- External model providers are untrusted services.
- LLM output is untrusted input and must pass schemas and policy checks.
- The SDK bridge accepts named protocol operations, not arbitrary shell code.
- Confirmatory scientific runs require explicit human approval.
- Capability, privacy, authorization, and spend limits are hard constraints.
- Content hashes detect mismatches under the documented local threat model;
  they are not digital signatures.

## Logging

The platform's shared logging and redaction utilities must be used for request,
agent, provider, optimizer, and fallback events. Logs should contain identifiers,
status, timing, token counts, and safe metadata—not request bodies, credentials,
headers, prompts, or documents.

## Reporting a vulnerability

Do not open a public issue containing exploit details or secret material. Contact
the repository owner privately with:

- affected commit and component;
- minimal reproduction without real credentials;
- impact and preconditions;
- suggested containment if known.

Preserve evidence safely and avoid destructive testing against third-party
providers or infrastructure.

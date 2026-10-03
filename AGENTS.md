# EigenBrains Hackathon Agent Rules

## Security

- Never read, display, copy, summarize, or transmit `.env`, `.env.*`, API keys, tokens, credentials, private keys, browser profiles, or OS credential stores.
- Never commit secrets.
- Use `.env.example` with placeholders only.
- Do not access files outside this repository unless explicitly asked.
- Do not upload repository files to external services unless explicitly required.

## Changes

- Prefer small, reversible edits.
- Ask before deleting files, changing authentication, modifying deployment credentials, or making destructive changes.
- Ask before installing large or unnecessary dependencies.
- Preserve existing architecture unless there is a clear reason to change it.

## Quality

- Run relevant tests after meaningful changes.
- Do not claim a feature works unless it is actually implemented.
- Avoid mock/random outputs in production paths.
- Keep frontend contracts synchronized with backend routes.
- Document non-obvious technical decisions.

## Hackathon priorities

- Optimize for a working end-to-end product.
- Keep the challenge-specific technical core separate from boilerplate.
- Prefer measurable behavior over architectural complexity.
- Preserve traceability, uncertainty, and failure handling where relevant.

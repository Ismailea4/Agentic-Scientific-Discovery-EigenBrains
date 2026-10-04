# Agentic-Scientific-Discovery-EigenBrains
An Omnigent-orchestrated AI lab built for the Hack-Nation 7th Challenge 03 to automate experimental workflows, coordinate specialist agents, and accelerate scientific discovery.

## Current evidence

- Two recorded Omnigent discovery loops with immutable ledgers and artifacts.
- A frozen acceleration protocol comparing information-gain selection with a
  conventional fixed sweep and a larger reference design.
- 63 Python tests covering the scientific core, ledger, planner, statistics,
  agent-facing contracts, and public SDK.

See [`discolab/README.md`](discolab/README.md) for the research system and
recorded runs.

## SDK

[`sdk/README.md`](sdk/README.md) documents the multi-language SDK:

- Python: authoritative research lifecycle and AI orchestration API.
- Rust: typed bridge client plus native high-throughput telemetry kernels.
- Julia: bridge client plus decision-theory and statistical mathematics.

All three languages share the versioned JSONL contract in
[`sdk/protocol/v1/schema.json`](sdk/protocol/v1/schema.json); the scientific
logic and ledger transition guards remain authoritative in Python.
Detailed method and failure semantics are in
[`docs/SDK_CONTRACTS.md`](docs/SDK_CONTRACTS.md).

The agents' research doctrine is documented in
[`docs/SCIENTIFIC_RESEARCH_PLAYBOOK.md`](docs/SCIENTIFIC_RESEARCH_PLAYBOOK.md).

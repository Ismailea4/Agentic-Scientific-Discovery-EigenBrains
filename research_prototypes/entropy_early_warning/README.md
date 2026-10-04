# Entropy early-warning study (sealed)

Do population-entropy dynamics give early warning of evolutionary-search
stagnation beyond fitness history alone? **Result: no meaningful gain on
held-out landscapes; the effect is landscape-dependent.** Full report:
[`docs/SEALED_ENTROPY_EARLY_WARNING_RESULT.md`](../../docs/SEALED_ENTROPY_EARLY_WARNING_RESULT.md).

| File | Purpose |
|---|---|
| `protocol.yaml` | frozen protocol, committed before any data (`eac845c`) |
| `ewstudy.py` | SDK `@experiment` definitions: simulation, analyses, benchmark, parity check |
| `run_study.py` | driver; development stage by default, held-out only with `--confirm` |
| `rust/` | native entropy audit and timing (evidence run via the sidecar) |
| `julia/analysis.jl` | AUROC recomputation and Obuchowski clustered interval |
| `evidence/entropy-early-warning-v1.zip` | sealed bundle of the 9 study runs |
| `evidence/study-summary.json` | machine-readable summary of the sealed run |

```bash
# verify the sealed evidence
cd discolab && python -m discolab.sdk_cli verify-bundle ../research_prototypes/entropy_early_warning/evidence/entropy-early-warning-v1.zip
# re-run the study in a fresh store (from the repository root)
python research_prototypes/entropy_early_warning/run_study.py --root research_prototypes/entropy_early_warning/output/rerun --confirm
```

Generated stores go under the ignored `output/` directory.

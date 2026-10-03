# EigenBrains evidence-first demo

## One-sentence thesis

EigenBrains treats models as correlated computational assets and buys a second opinion only when the measured reduction in error justifies its cost and latency.

## Five-beat presentation

1. **The problem - 20 seconds.** A larger agent graph is not automatically a better system. Models can fail together, and every extra call adds cost and latency.
2. **The first evidence - 35 seconds.** Show the 120-call paired pilot: GPT-OSS/DeepSeek failure correlation `0.872` and Jaccard `0.80`; GPT-OSS/Qwen correlation `0.596` and mutual rescues. Label these estimates exploratory (`n=24`).
3. **The decision policy - 40 seconds.** Show Qwen answering first. Display only measurable escalation signals: schema failure, explicit abstention, task risk, task family, and a tuning-derived historical error bound. Ground truth is never a routing input.
4. **The economic result - 45 seconds.** Compare Qwen-only, GPT-OSS-only, always-both, Qwen -> selective GPT-OSS, and the reverse policy. Lead with measured quality, severe failures, escalation rate, rescue/damage, cost, latency, and uncertainty. The key chart is selective escalation versus always-both cost/latency.
5. **The adaptation story - 20 seconds.** Generic results become weak priors with effective sample strength `kappa=4`; challenge observations rapidly override them.

## Required evidence card

```text
Qwen -> selective GPT-OSS

quality:                         measured value + 95% interval
severe-failure probability:      measured value + interval
escalation probability:          measured value
second-model rescue probability: measured value + interval
damage to correct first answers: measured value + interval
cost versus Qwen-only:           measured delta
latency versus Qwen-only:        measured delta
cost saving versus always-both:  measured saving
latency saving versus always:    measured saving
```

Do not replace missing values with illustrative numbers. Until the compact architecture study runs, render them as `awaiting approved experiment`.

## Claim ladder

- **Supported now:** the pilot observed different failure-overlap structures among the tested models.
- **To test next:** selective Qwen -> GPT escalation captures most of the quality/risk benefit of always-both while spending less.
- **Not yet supported:** every multi-agent architecture beats a single model; all A0-A6 are empirically ranked; critic or verifier value generalizes to the challenge.

## Keep off the main stage

- A0-A6 implementation details unless a judge asks.
- Long lists of statistical methods.
- Unqualified rankings from 24 cases.
- Claims that provider failures are reasoning failures.
- Utility-weighted conclusions without showing raw quality, cost, latency, and risk components.

## Closing line

> We measured which systems fail together, learned the marginal value of a second opinion, and invoke additional intelligence only when its expected reduction in error justifies its cost and latency.

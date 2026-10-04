## Final report

**Question.** Does population-entropy dynamics warn of GA stagnation beyond fitness history? Can that signal drive a mutation intervention that recovers faster after the landscape changes?

**Evidence (OpenAlex-verified, found by the literature agent).**
- Entropy-adaptive GAs: W2387338990, W2040936185.
- Adaptive mutation baselines: W2167823546, W1661890235.
- Dynamic-environment baselines: W2132340807, W2128702894.
- Early-warning context: W3200303296, W4380442874.
- Prior work adapts operators reactively. The lit review found no prior work on a frozen predictive risk model that times the intervention. That novelty claim rests on the literature agent's search, not on a systematic review.

**Hypotheses (posteriors before → after).**

| Hypothesis | Posterior | Status |
|---|---|---|
| H1: entropy adds to fitness | 0.5 → 0.975 | supported |
| H2: dispersion adds to fitness | 0.5 → 0.975 | supported |
| H3: fitness spread adds to fitness | 0.5 → 0.019 | labelled "refuted" |
| H4: B3 beats strongest non-oracle baseline | 0.5 → 0.311 | inconclusive |
| H5: entropy adds beyond dispersion | 0.5 → 0.976 | supported |
| H6: B3 beats rate-matched fixed (timing, not rate) | 0.5 → 0.320 | inconclusive |
| H7: dispersion-driven controller beats baseline | 0.5 → 0.49 | untested |

- H5–H7 are agent-generated hypotheses.
- H3's low posterior is an artefact of the update rule. Its CI [-0.0096, 0.0164] includes effects above the 0.01 smallest effect of interest, so it is unresolved.
- H4 and H6 were tested by the same contrast, so they are not independent evidence.
- H4's posterior moved 0.5 → 0.49 → 0.311. The first step was a coupling update from H1, and E7 supplied the second.
- H7 moved only through that coupling.

**Experiments.**
- **E1** (prediction, leave-one-landscape-out, 72 runs):
  - Entropy: ΔAUROC 0.101 [0.0695, 0.1342].
  - Dispersion: 0.0256 [0.0173, 0.0343].
  - Fitness spread: 0.0038 [-0.0096, 0.0164].
- **E4** (16 seeds, 96 runs): fitness+dispersion+entropy minus fitness+dispersion ΔAUROC 0.0685 [0.0508, 0.0859]. AUROC went from 0.794 to 0.8625.
- **E7** (control, 2 landscapes, 10 seeds):
  - B3 vs B0_fixed_x0.8: RMST reduction -1.49 generations [-4.76, 2.2812], inconclusive.
  - Both B3 (-3.98 [-7.4502, -0.73]) and fixed x0.8 (-5.47 [-7.3203, -3.66]) beat B0_fixed.
  - B3 rescued 34 and damaged 14 runs. x0.8 rescued 32 and damaged 8.
- Total compute used was 37.6 s of 1800 s.

**What the lab learned.**
- **Prediction.** At development stage, entropy adds ranking information beyond fitness history, and beyond dispersion.
- **Control.** That gain did not translate into faster recovery. A constant mutation rate matched to B3's average rate recovered as well or better than B3. B3's benefit may be a lower mutation rate, not better timing.
- **Surprise.** Better AUROC was assumed to imply better intervention timing. E7 reopens that assumption.

**Next experiment.** E8 (B3 vs the dispersion controller B3d vs a fixed rate, H4+H7), as recorded in my decision. Before this result I would have run E5, the narrow timing-vs-rate test. The critic recommends a larger version with more seeds, held-out landscapes, a fixed-rate sweep and a hypermutation baseline. I have not run or scored that design.

**Limitations and validation still needed.**
- Everything is development stage. Landscapes were reused, and AUROC CIs may be too narrow because test points are autocorrelated within runs.
- Stagnation prevalence is about 3%, and Brier barely moves (0.0299 → 0.0291 in E1).
- Some of the AUROC gain may come from detecting stagnation already under way, not from early warning. No lead-time or false-alarm analysis has been done.
- The control test used 2 landscapes and 10 seeds, with a CI about 7 generations wide.
- Recovery is censored at 60 generations, so CVaR90 is uninformative.
- The x0.8 comparator was chosen post hoc. Hypermutation and immigrant baselines were not run.
- No confirmatory (held-out) test has been run. E6 covers only H1 and H2, and no confirmatory test is planned for H5.
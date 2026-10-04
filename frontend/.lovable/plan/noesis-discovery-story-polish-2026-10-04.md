# Noesis "Discovery Story" polish

## Goal
One flowing, connected narrative in the Discovery Loop showing: question → competing experiments → value-of-information ranking → agent choice → computation → result with uncertainty → belief update → changed next decision → impact → provenance.

## What gets built
1. **Discovery Story stage** (top of Discovery Loop), ten connected steps joined by an animated glowing line, each revealing as you scroll:
   - Research question in large, bold type.
   - Two top candidate experiments side by side (from the latest selection round).
   - Expected information gain / utility ranking, shown as math scores with a bar.
   - Agent choice: highlights the chosen experiment, marks whether it matched the top score, and quotes the PI's reason.
   - Computation: terminal-style panel replaying the run's tool calls and progress (labelled RECORDED when replaying, LIVE when streaming).
   - Result: error and entropy curves drawn left to right, effect size with 95% interval, verdict badge.
   - Belief update: before/after posterior bars for each hypothesis tested.
   - Next decision: "before → after" card showing how the plan changed.
   - Impact card: large glowing compute-saving number.
   - Provenance strip: pre-registration hash and experiment ids in small monospace; language-chain badge.
2. **Agent handoffs**: pulse traveling along graph edges plus a soft glow on the receiving agent.
3. **Sound**: small sound helper (tick on handoff, quiet hum during computation, chime on verdict), generated in the browser, with a Mute toggle in the header; muted by default until clicked.
4. **Look**: dark glass panels with blurred cyan/magenta/deep-blue background glow; smooth glide for collapsible sections; fade-and-rise for new data. Respects reduced-motion.

## Honesty rules
- The "35.15% compute saving" and "Python → Rust → Julia" values are not in the lab feed. They will be shown labelled BENCHMARK (from your team's claim) unless you send me where they come from; everything else uses real run data, or SAMPLE when no lab is connected.

## Technical details
- New `src/noesis/lab/DiscoveryStory.tsx` built from `LabState.rounds`, `trajectories`, `decisions`, `analyses`, `prereg_sha256`, and `labApi.experiment` curves; sample fallback in `fixtures.ts`.
- `src/noesis/hooks/useSound.ts` using Web Audio (no files), mute stored in localStorage.
- CSS additions in `src/noesis/index.css` (stroke-dashoffset line drawing, edge pulse keyframes, glass tokens). No backend or feed changes.

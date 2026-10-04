# Neosis frontend enhancement plan

## Goal
Bring the existing frontend into this project as faithfully as possible under its new name, Neosis, preserve its visual identity and working interactions, and strengthen the presentation around Challenge 03 without changing backend code or API behavior.

## What will be built

### 1. Port the existing experience as Neosis
- Recreate the current sidebar, toolbar, command palette, inspector, team panel, themes, and reduced-motion behavior.
- Replace the existing narrative with the rubric’s required loop: Question → Evidence → Hypothesis → Experiment → Result → Updated decision.
- Rename and adapt the workspaces as Discovery Loop, Hypotheses, Human Approval Gate, and Research Record, while retaining sample/live evidence labels and responsive behavior.
- Reuse the existing team image, icon language, charts, graph presentation, copy, and interaction patterns from the repository.

### 2. Make the challenge story explicit
- Reframe the opening and narrative copy around EigenBrains as an Omnigent-orchestrated scientific discovery lab.
- Clearly surface the required loop: Question → Evidence → Hypothesis → Experiment → Result → Updated decision.
- Show specialist-agent roles, handoffs, tool permissions, and the point where experimental evidence changes the next decision.
- Add clear Omnigent orchestration context without implying unsupported capabilities.
- Design scientific data views for literature citations, biological and scientific hypotheses, experiment protocols, confidence scores, uncertainty, and evidence-linked decisions expected from Databricks Omnigent.
- Redesign the Inspector and Trace presentations as readable, polished scientific research records that handle long-form text, citations, structured evidence, and dense provenance without truncating meaning.

### 3. Strengthen judging evidence
- Add a concise challenge overview showing the scientific bottleneck, measurable outcome, observed acceleration, and next experiment.
- Present existing benchmark evidence and uncertainty honestly, using only values and claims already supported by repository reports or live API responses.
- Keep SAMPLE, BENCHMARK, and LIVE states visually distinct.
- Surface citations/source references, reproducibility details, controls, and human-approval gates where the existing evidence supports them.
- Avoid fabricated results; unavailable metrics remain clearly marked as awaiting an approved experiment.

### 4. Preserve all backend boundaries
- Keep the existing request/response contracts for health, capabilities, architectures, Pareto frontier, policy evaluation, fallback resolution, and heartbeat streaming.
- Make no changes to backend files, schemas, agent execution, experiment logic, or endpoint behavior.
- Retain same-origin `/api` and `/health` calls so the frontend continues to work with the existing backend deployment.
- Keep frontend fallbacks explicit and labeled rather than presenting fixture data as live evidence.
- Keep current contracts working while making the presentation layer ready for richer scientific payloads from the planned Databricks Omnigent connection, without implementing or altering that connection.

### 5. Adapt safely to this app framework
- Implement the experience with TanStack routes while preserving the same user-facing views and navigation behavior.
- Keep browser-only animation, theme storage, and event streaming out of server rendering paths.
- Build a semantic light/dark design-token system matching the current EigenBrains aesthetic.
- Add route-specific metadata and retain accessible keyboard, focus, contrast, and reduced-motion behavior.

### 6. Verify the complete demonstration
- Check desktop, tablet, and mobile layouts in light and dark themes.
- Exercise navigation, command palette, inspector, theme switching, agent selection, estimation controls, policy display, and live trace behavior.
- Verify loading, offline, empty, sample, benchmark, and live states without requiring backend modifications.
- Verify long citations, multi-paragraph hypotheses, scientific notation, confidence intervals, provenance metadata, and extensive trace entries remain legible across screen sizes.
- Confirm the final challenge narrative can be demonstrated coherently in approximately two minutes.

## Technical scope
- Frontend source, styling, local presentation data, and assets only.
- The GitHub `codebase` branch is the source of truth for the existing interface and API contracts.
- No database, authentication, new backend endpoint, or backend proxy implementation will be introduced.
- Existing supported evidence from repository documentation may be represented as static frontend content with source attribution; it will not be altered or promoted to live data.

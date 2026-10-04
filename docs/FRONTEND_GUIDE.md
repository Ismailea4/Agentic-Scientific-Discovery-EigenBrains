# Frontend guide

The frontend is a React 18 and Vite control surface designed to explain the
EigenBrains workflow while remaining explicit about which values are live,
measured, replayed, or illustrative.

## Information architecture

The application exposes five hash-routed views:

| Route | View | Purpose |
|---|---|---|
| `#/home` | Home | Seven-chapter product and research narrative |
| `#/agents` | Agents | Agent graph, routing, capabilities, and fallbacks |
| `#/estimation` | Estimation | Quality/cost/latency/risk tradeoffs and frontier |
| `#/security` | Security | Capability and allowed/denied path explanation |
| `#/trace` | Trace | Execution and evidence trace |

Legacy hash aliases are mapped in `src/hooks/useHashView.ts`. Add new stable
routes there rather than scattering hash parsing across components.

## Application shell

`src/App.tsx` owns:

- active view and hash navigation;
- dark/light/system theme state persisted under `eb-theme`;
- sidebar, toolbar, inspector, command palette, and Team dialog;
- home scroll preservation when entering and leaving a workspace;
- source-aware rightward workspace materialization;
- backend health state;
- keyboard commands.

Keyboard shortcuts:

| Shortcut | Action |
|---|---|
| `Ctrl/Cmd + K` | Toggle command palette |
| `Ctrl/Cmd + I` | Toggle inspector |

The sidebar uses semantic navigation with `aria-current`. Modal and overlay
components must preserve focus, keyboard dismissal, labels, and reduced-motion
behavior.

## Narrative chapters

The home story has seven conceptual chapters:

1. Ask
2. Understand
3. Assemble
4. Estimate
5. Secure
6. Verify
7. Deliver

The app stores the home scroll position before opening another view and restores
it on return. This is why returning from a workspace preserves the user's last
chapter instead of resetting to chapter one.

On narrow viewports or when `prefers-reduced-motion: reduce` matches,
`useQuietMotion` replaces the cinematic scroll behavior with a quieter
presentation. New animation must respect this hook and must not be required to
understand or operate the interface.

## Visual system

The intended balance is:

- restrained neutral UI for structure and long reading;
- selective translucent glass for command, analysis, inspector, and key-result
  surfaces;
- limited cyan, violet, and amber light for hierarchy and active state.

Avoid making every container translucent or luminous. Text contrast and state
legibility have priority over visual effect. Motion should clarify origin,
continuity, or progression: unfold from a source, draw a plot progressively, or
settle a panel. Do not add decorative bouncing or endless loops.

## Data provenance in the UI

`src/dev/fixtures.ts` is development-only. It declares in its file header that
its figures are hand-written layout examples. Production evidence views must
not import it.

Every rendered quantity should expose or inherit an evidence label:

- `SAMPLE` for hand-authored fixture data;
- `REPLAY` for counterfactual policy application;
- `BENCHMARK` for a frozen measured study;
- `PROVIDER_BACKED` for an executed architecture step;
- `LIVE` for current telemetry.

Never remove a sample marker merely to make a demo appear more complete.

## API access

Use the shared client in `src/api/client.ts`. It:

- performs same-origin fetches;
- parses JSON responses;
- converts non-2xx responses into `ApiError` with status, code, message, and
  details;
- represents network failure with status `0`.

Endpoint wrappers live in `src/api/system.ts`; response and request mirrors live
in `src/api/types.ts`. When the backend contract changes, update these files and
the backend contract test in the same change.

The development server proxies `/api` and `/health` to port 8000. Avoid hardcoded
backend origins in components.

## Adding a workspace

1. Add the view identifier to `AppView` and `ROUTES`.
2. Add navigation metadata to `NAV`.
3. Create a workspace-level component under `src/experiences/` or `src/views/`.
4. Render it in the `stage-main` switch in `App.tsx`.
5. Add typed API functions rather than calling `fetch` directly.
6. Define empty, loading, error, sample, and live states.
7. Add the command-palette entry.
8. Verify inspector behavior, theme contrast, keyboard access, and reduced
   motion.
9. Run typecheck and production build.
10. Capture fixed-viewport visual QA in dark and light themes.

Do not put provider credentials, scientific computation, policy enforcement, or
result mutation in a browser component.

## Visual QA

Standard checks:

```powershell
Set-Location .\frontend
npm ci
npm run typecheck
npm run build
npm run dev
```

The capture script uses a running Chromium DevTools endpoint. Its positional
arguments are:

```text
node scripts/capture-story.mjs <debug-endpoint> <output> <width> <height> <preset> <url> <theme>
```

Example:

```powershell
node .\scripts\capture-story.mjs `
  http://127.0.0.1:9223 `
  .\qa-screenshots\verification-dark `
  1440 900 story `
  http://127.0.0.1:5173/#/home `
  dark
```

The script records viewport, active chapter, horizontal overflow, and visible
title in addition to screenshots. Review at minimum:

- 1440 × 900 desktop;
- 1024 × 768 small desktop/tablet;
- 768 × 900 narrow tablet;
- 390 × 844 mobile;
- dark and light themes;
- Team dialog;
- all seven chapters;
- every workspace;
- reduced-motion or quiet mode.

## Accessibility checklist

- [ ] All icon-only buttons have accessible labels.
- [ ] Current navigation uses `aria-current`.
- [ ] Toggle state uses `aria-pressed` or `aria-expanded` where appropriate.
- [ ] Dialogs expose role/name and restore focus on close.
- [ ] Keyboard users can reach every control.
- [ ] Focus indication remains visible on glass surfaces.
- [ ] Status does not rely on color alone.
- [ ] Text remains readable over blooms and translucent backgrounds.
- [ ] Reduced motion removes nonessential transitions.
- [ ] Charts have textual values or summaries.
- [ ] Loading and error states are announced meaningfully.

## Performance guidance

- Keep animated blur and large backdrop filters limited to high-value surfaces.
- Prefer transforms and opacity for motion.
- Do not continuously redraw charts when values are unchanged.
- Memoize expensive derived view models, not trivial markup.
- Avoid adding dependencies for behavior already covered by small local hooks.
- Verify production output with `npm run build`; development responsiveness alone
  is not evidence of bundle health.

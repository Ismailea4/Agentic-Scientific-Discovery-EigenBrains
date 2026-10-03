# Visual QA captures

- `before/`: original connected-Chrome captures taken before the first polish pass.
- `after/`: the restrained light pass that served as the baseline for the cinematic update.
- `before-dark/`: frozen copy of that light baseline for direct before/after review.
- `after-dark/`: canonical 1440 x 900 Chromium captures of all seven cinematic glass states.
- `after-light/`: canonical 1440 x 900 Chromium captures of the equivalent premium light states.
- `team/` and `team-dark/`: the Team dialog in each appearance.
- `responsive/`: responsive checks for the earlier light pass.
- `responsive-dark/`: 1024 x 768, 768 x 900, and 390 x 844 checks for the dark pass.
- `responsive-light/`: mobile verification for the light Team surface.

The original connected-Chrome baseline in `before/` has a compositor scaling offset. Use `before-dark/` and `after-dark/` for accurate fixed-viewport comparison.

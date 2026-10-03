import { useEffect, useRef } from 'react';
import { ProgressiveText } from '../components/ProgressiveText';
import { AgentsExperience } from '../experiences/AgentsExperience';
import { EstimationExperience } from '../experiences/EstimationExperience';
import { SecurityExperience } from '../experiences/SecurityExperience';
import { TraceExperience } from '../experiences/TraceExperience';

const THRESHOLDS = [0, 0.12, 0.26, 0.42, 0.58, 0.74, 0.88];

const COPY = [
  ['Ask', 'Intelligence that chooses how to think.'],
  ['Understand', 'Every agent earns its place.'],
  ['Assemble', 'A deliberate system, not a crowd.'],
  ['Estimate', 'Intelligence has a cost.'],
  ['Secure', 'Security is structural.'],
  ['Verify', 'Know when not to answer.'],
  ['Deliver', 'Built to be inspected.'],
] as const;

function chapterFor(progress: number): number {
  let chapter = 0;
  for (let index = 0; index < THRESHOLDS.length; index += 1) {
    if (progress >= THRESHOLDS[index]) chapter = index;
  }
  return chapter;
}

export function Home({ quiet, chapter, onChapterChange }: { quiet: boolean; chapter: number; onChapterChange: (chapter: number) => void }) {
  const runRef = useRef<HTMLElement>(null);
  const chapterRef = useRef(chapter);

  useEffect(() => { chapterRef.current = chapter; }, [chapter]);

  useEffect(() => {
    if (quiet) {
      onChapterChange(6);
      document.documentElement.style.setProperty('--story', '1');
      return;
    }
    let frame = 0;
    const update = () => {
      frame = 0;
      const run = runRef.current;
      if (!run) return;
      const rect = run.getBoundingClientRect();
      const distance = Math.max(1, rect.height - window.innerHeight);
      const progress = Math.max(0, Math.min(1, -rect.top / distance));
      document.documentElement.style.setProperty('--story', progress.toFixed(4));
      const next = chapterFor(progress);
      if (next !== chapterRef.current) {
        chapterRef.current = next;
        onChapterChange(next);
      }
    };
    const schedule = () => {
      if (!frame) frame = window.requestAnimationFrame(update);
    };
    update();
    window.addEventListener('scroll', schedule, { passive: true });
    window.addEventListener('resize', schedule);
    return () => {
      window.removeEventListener('scroll', schedule);
      window.removeEventListener('resize', schedule);
      if (frame) window.cancelAnimationFrame(frame);
    };
  }, [onChapterChange, quiet]);

  if (quiet) {
    return (
      <main id="workspace" className="quiet-story" aria-label="EigenBrains product story">
        {COPY.map(([label, text], index) => (
          <section className="quiet-chapter" key={label}>
            <StoryHeading label={label} text={text} active reducedMotion />
            {index === 1 ? <UnderstandingNode /> : null}
            {index === 2 || index === 6 ? <AgentsExperience mode={index === 6 ? 'workspace' : 'narrative'} /> : null}
            {index === 3 ? <EstimationExperience mode="narrative" /> : null}
            {index === 4 ? <SecurityExperience mode="narrative" /> : null}
            {index === 5 ? <TraceExperience mode="narrative" /> : null}
          </section>
        ))}
      </main>
    );
  }

  return (
    <main id="workspace" className="story-run" ref={runRef} aria-label="EigenBrains product story">
      <div className="story-pin">
        <StoryGeometry chapter={chapter} />
        {COPY.map(([label, text], index) => (
          <section className={index === chapter ? `story-scene story-scene-${index} is-on` : `story-scene story-scene-${index}`} aria-hidden={index !== chapter} key={label}>
            <StoryHeading label={label} text={text} active={index === chapter} />
            <div className="story-object">
              {index === 0 ? (
                <div className="hero-anchor" aria-hidden="true">
                  <span className="hero-spine" />
                  <span className="hero-orbit"><i /></span>
                  <small>intent enters the system</small>
                </div>
              ) : null}
              {index === 1 ? <UnderstandingNode /> : null}
              {index === 2 ? <AgentsExperience mode="narrative" /> : null}
              {index === 3 ? <EstimationExperience mode="narrative" /> : null}
              {index === 4 ? <SecurityExperience mode="narrative" /> : null}
              {index === 5 ? <TraceExperience mode="narrative" /> : null}
              {index === 6 ? <AgentsExperience mode="workspace" /> : null}
            </div>
          </section>
        ))}
        <div className="story-index" aria-hidden="true">{String(chapter + 1).padStart(2, '0')} / 07</div>
      </div>
    </main>
  );
}

function StoryHeading({ label, text, active, reducedMotion = false }: { label: string; text: string; active: boolean; reducedMotion?: boolean }) {
  return (
    <header className="story-copy">
      <p className="eyebrow">{label}</p>
      <h2><ProgressiveText text={text} mode="word" speed={36} delay={56} trigger={active} reducedMotion={reducedMotion} /></h2>
    </header>
  );
}

function UnderstandingNode() {
  return (
    <div className="understanding-object">
      <span className="understanding-line" aria-hidden="true" />
      <button type="button" className="agent-node is-on-path"><span className="node-status"><i className="live-dot is-running" />Available</span><span className="node-label">Reasoning</span></button>
    </div>
  );
}

function StoryGeometry({ chapter }: { chapter: number }) {
  return (
    <svg className={`story-geometry chapter-${chapter}`} viewBox="0 0 1000 700" preserveAspectRatio="none" aria-hidden="true">
      <path className="geometry-spine" pathLength="1" d="M 500 218 C 500 268, 500 304, 500 354" />
      <path className="geometry-left" pathLength="1" d="M 500 278 C 500 326, 414 326, 414 374 C 414 416, 348 416, 348 466" />
      <path className="geometry-right" pathLength="1" d="M 500 278 C 500 326, 586 326, 586 374 C 586 416, 652 416, 652 466" />
    </svg>
  );
}

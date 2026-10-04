import { useEffect, useRef } from 'react';
import { ProgressiveText } from '../components/ProgressiveText';
import { AgentsExperience } from '../experiences/AgentsExperience';
import { EstimationExperience } from '../experiences/EstimationExperience';
import { SecurityExperience } from '../experiences/SecurityExperience';
import { TraceExperience } from '../experiences/TraceExperience';

const THRESHOLDS = [0, 0.16, 0.34, 0.52, 0.7, 0.86];

const COPY = [
  ['Question', 'Start with a falsifiable scientific question.'],
  ['Evidence', 'Specialists retrieve, cite, and challenge the literature.'],
  ['Hypothesis', 'A learning mechanism becomes a ranked prediction.'],
  ['Experiment', 'A human approves the discriminating protocol.'],
  ['Result', 'Observed evidence is preserved with its provenance.'],
  ['Updated decision', 'Every result changes what Noesis does next.'],
] as const;

function chapterFor(progress: number): number {
  let chapter = 0;
  for (let index = 0; index < THRESHOLDS.length; index += 1) {
    const threshold = THRESHOLDS[index];
    if (threshold !== undefined && progress >= threshold) chapter = index;
  }
  return chapter;
}

export function Home({ quiet, chapter, onChapterChange }: { quiet: boolean; chapter: number; onChapterChange: (chapter: number) => void }) {
  const runRef = useRef<HTMLElement>(null);
  const chapterRef = useRef(chapter);

  useEffect(() => { chapterRef.current = chapter; }, [chapter]);

  useEffect(() => {
    if (quiet) {
      onChapterChange(5);
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
      <main id="workspace" className="quiet-story" aria-label="Noesis scientific discovery loop">
        {COPY.map(([label, text], index) => (
          <section className="quiet-chapter" key={label}>
            <StoryHeading label={label} text={text} active reducedMotion />
            {index === 1 ? <AgentsExperience mode="narrative" /> : null}
            {index === 2 ? <EstimationExperience mode="narrative" /> : null}
            {index === 3 ? <SecurityExperience mode="narrative" /> : null}
            {index === 4 ? <TraceExperience mode="narrative" /> : null}
            {index === 5 ? <AgentsExperience mode="workspace" /> : null}
          </section>
        ))}
      </main>
    );
  }

  return (
    <main id="workspace" className="story-run" ref={runRef} aria-label="Noesis scientific discovery loop">
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
                  <small>question enters the discovery loop</small>
                </div>
              ) : null}
              {index === 1 ? <AgentsExperience mode="narrative" /> : null}
              {index === 2 ? <EstimationExperience mode="narrative" /> : null}
              {index === 3 ? <SecurityExperience mode="narrative" /> : null}
              {index === 4 ? <TraceExperience mode="narrative" /> : null}
              {index === 5 ? <AgentsExperience mode="workspace" /> : null}
            </div>
          </section>
        ))}
        <div className="story-index" aria-hidden="true">{String(chapter + 1).padStart(2, '0')} / 06</div>
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

function StoryGeometry({ chapter }: { chapter: number }) {
  return (
    <svg className={`story-geometry chapter-${chapter}`} viewBox="0 0 1000 700" preserveAspectRatio="none" aria-hidden="true">
      <path className="geometry-spine" pathLength="1" d="M 500 218 C 500 268, 500 304, 500 354" />
      <path className="geometry-left" pathLength="1" d="M 500 278 C 500 326, 414 326, 414 374 C 414 416, 348 416, 348 466" />
      <path className="geometry-right" pathLength="1" d="M 500 278 C 500 326, 586 326, 586 374 C 586 416, 652 416, 652 466" />
    </svg>
  );
}

import { useMemo } from 'react';

export function ProgressiveText({
  text,
  mode = 'word',
  speed = 42,
  delay = 0,
  trigger = true,
  blur = 5,
  reducedMotion = false,
  className,
}: {
  text: string;
  mode?: 'character' | 'word';
  speed?: number;
  delay?: number;
  trigger?: boolean;
  blur?: number;
  reducedMotion?: boolean;
  className?: string;
}) {
  const segments = useMemo(
    () => {
      const parts = mode === 'word' ? text.split(/(\s+)/) : Array.from(text);
      let order = -1;
      return parts.map((segment) => {
        if (segment.trim()) order += 1;
        return { segment, order: Math.max(0, order) };
      });
    },
    [mode, text],
  );

  return (
    <span className={className} aria-label={text}>
      {segments.map(({ segment, order }, index) => (
        <span
          aria-hidden="true"
          className={trigger || reducedMotion ? 'progressive-token is-visible' : 'progressive-token'}
          key={`${segment}-${index}`}
          style={{
            ['--token-delay' as string]: `${reducedMotion ? 0 : delay + order * speed * 0.72 + (order % 3) * 7}ms`,
            ['--token-blur' as string]: `${reducedMotion ? 0 : blur}px`,
          }}
        >
          {segment}
        </span>
      ))}
    </span>
  );
}

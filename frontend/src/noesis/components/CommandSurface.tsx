import { useEffect, useState, type FormEvent } from 'react';
import { labApi } from '../api/lab';
import { useLab } from '../lab/LabContext';
import { useShell } from './shell';

const SAMPLE_QUESTION = 'Does population entropy give early warning of genetic-algorithm stagnation beyond the fitness history?';
import { IconArrow, IconMic, IconPlus } from './icons';
import { Popover, PopoverContent, PopoverTrigger, Tooltip, TooltipContent, TooltipTrigger } from './overlay';
import { cx } from './ui';

export function CommandSurface({ docked }: { docked: boolean }) {
  const [message, setMessage] = useState('');
  const [revealed, setRevealed] = useState(false);
  const lab = useLab();
  const { navigate } = useShell();
  const [questions, setQuestions] = useState<{ id: string; kind: string; question: string }[]>([]);

  useEffect(() => {
    if (lab.status !== 'connected') { setQuestions([]); return; }
    let cancelled = false;
    Promise.all(lab.sources.map((src) => labApi.state(lab.baseUrl, src.id).then((st) => ({ id: src.id, kind: src.kind as string, question: st.question })).catch(() => null)))
      .then((rows) => { if (!cancelled) setQuestions(rows.filter((r): r is { id: string; kind: string; question: string } => r !== null)); });
    return () => { cancelled = true; };
  }, [lab.baseUrl, lab.sources, lab.status]);

  const open = (sourceId: string | null) => {
    if (sourceId) lab.setSourceId(sourceId);
    navigate('discovery');
  };

  const submit = (event: FormEvent) => {
    event.preventDefault();
    setMessage('Question staged for the next Omnigent discovery run.');
  };

  return (
    <div className={cx('command-surface-wrap', docked ? 'is-dock' : 'is-float')}>
      <form className="command-surface material-pop" onSubmit={submit}>
        <Popover>
          <PopoverTrigger label="Add context" className="command-action">
            <IconPlus />
          </PopoverTrigger>
          <PopoverContent title="Context">
            <p className="quiet">Attach literature, datasets, protocols, or prior results.</p>
          </PopoverContent>
        </Popover>
        <input
          aria-label="Ask Noesis a research question"
          placeholder="Ask a falsifiable scientific question…"
          onFocus={() => setRevealed(true)}
          onChange={() => message && setMessage('')}
        />
        <Tooltip>
          <TooltipTrigger>
            <button type="button" className="btn btn-icon command-action" aria-label="Microphone" aria-disabled="true">
              <IconMic />
            </button>
          </TooltipTrigger>
          <TooltipContent>No input device registered</TooltipContent>
        </Tooltip>
        <button type="submit" className="btn btn-icon command-submit" aria-label="Submit">
          <IconArrow />
        </button>
      </form>
      {revealed && (
        <div className="question-chips" aria-label="Questions already studied">
          {questions.length ? questions.map((q) => (
            <button key={q.id} type="button" className="question-chip" onClick={() => open(q.id)}>
              <small>{q.kind === 'live' ? 'Live lab' : 'Recorded run'} · {q.id.split('/')[1]}</small>
              {q.question.length > 120 ? `${q.question.slice(0, 118)}…` : q.question}
            </button>
          )) : (
            <button type="button" className="question-chip" onClick={() => open(null)}>
              <small>Sample</small>{SAMPLE_QUESTION}
            </button>
          )}
        </div>
      )}
      <p className={cx('command-message', message && 'is-visible')} aria-live="polite">{message}</p>
    </div>
  );
}

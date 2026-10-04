import { useState, type FormEvent } from 'react';
import { IconArrow, IconMic, IconPlus } from './icons';
import { Popover, PopoverContent, PopoverTrigger, Tooltip, TooltipContent, TooltipTrigger } from './overlay';
import { cx } from './ui';

export function CommandSurface({ docked }: { docked: boolean }) {
  const [message, setMessage] = useState('');

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
      <p className={cx('command-message', message && 'is-visible')} aria-live="polite">{message}</p>
    </div>
  );
}

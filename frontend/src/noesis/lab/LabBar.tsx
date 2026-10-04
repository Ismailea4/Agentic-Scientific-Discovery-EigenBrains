import { useState } from 'react';
import { Popover, PopoverContent, PopoverTrigger } from '../components/overlay';
import { StatusBadge } from '../components/ui';
import { useLab } from './LabContext';
import { useSound } from '../hooks/useSound';

export function sourceLabel(kind: 'live' | 'record' | undefined) {
  return kind === 'live' ? 'LIVE' : kind === 'record' ? 'RECORD' : 'SAMPLE';
}

/** Connection + source picker shown above every lab workspace. */
export function LabBar() {
  const lab = useLab();
  const [draft, setDraft] = useState<string | null>(null);
  const value = draft ?? lab.baseUrl;
  const kind = lab.source?.kind;
  const sound = useSound();

  return (
    <div className="lab-bar" role="region" aria-label="Discovery lab connection">
      <span className={`lab-mode lab-mode-${kind ?? 'sample'}`}>{sourceLabel(kind)}</span>
      {lab.status === 'connected' && lab.sources.length > 0 ? (
        <label className="lab-source">
          <span className="quiet">Source</span>
          <select value={lab.sourceId ?? ''} onChange={(event) => lab.setSourceId(event.target.value || null)}>
            {lab.sources.map((s) => (
              <option key={s.id} value={s.id}>
                {s.kind === 'live' ? 'Live · ' : 'Record · '}{s.id.split('/')[1]} ({s.experiments} exp.)
              </option>
            ))}
            <option value="">Sample (no lab data)</option>
          </select>
        </label>
      ) : (
        <span className="quiet lab-hint">
          {lab.status === 'checking' ? 'Connecting to the discovery lab…' : 'Lab offline — showing labelled samples.'}
        </span>
      )}
      {lab.streaming && kind === 'live' ? <StatusBadge tone="ok">streaming</StatusBadge> : null}
      <span className="lab-spacer" />
      <StatusBadge tone={lab.status === 'connected' ? 'ok' : lab.status === 'checking' ? 'idle' : 'bad'}>
        {lab.status === 'connected' ? 'Lab connected' : lab.status === 'checking' ? 'Checking' : 'Lab offline'}
      </StatusBadge>
      <button type="button" className="btn lab-settings" aria-pressed={sound.on} onClick={sound.toggle}>{sound.on ? 'Sound on' : 'Muted'}</button>
      <Popover>
        <PopoverTrigger label="Lab connection settings" className="btn lab-settings">Connection</PopoverTrigger>
        <PopoverContent title="Discovery lab feed">
          <form
            className="lab-form"
            onSubmit={(event) => { event.preventDefault(); lab.setBaseUrl(value); setDraft(null); lab.refresh(); }}
          >
            <p className="quiet">Leave empty to use the feed on this machine (port 8765). Paste a public address, such as a tunnel link, to reach a teammate's lab.</p>
            <input
              type="url"
              placeholder="https://your-lab-tunnel.example.com"
              value={value}
              onChange={(event) => setDraft(event.target.value)}
              aria-label="Lab feed address"
            />
            <div className="lab-form-actions">
              <button type="button" className="btn" onClick={() => { lab.setBaseUrl(''); setDraft(null); lab.refresh(); }}>Use local</button>
              <button type="submit" className="btn btn-primary">Connect</button>
            </div>
            {lab.error ? <p className="lab-error" role="status">{lab.error}</p> : null}
          </form>
        </PopoverContent>
      </Popover>
    </div>
  );
}

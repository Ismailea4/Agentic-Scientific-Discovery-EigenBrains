import { useEffect, useId, useRef } from 'react';
import { createPortal } from 'react-dom';
import teamPicture from '../assets/team-picture.jpeg';
import { IconClose } from './icons';

const MEMBERS = [
  { name: 'El Yazid TEBBAA', role: 'Product & systems' },
  { name: 'Saâd QACIF', role: 'Research & experience' },
  { name: 'Ismail ELADRAOUI', role: 'AI & engineering' },
] as const;

export function TeamPanel({ open, onClose }: { open: boolean; onClose: () => void }) {
  const titleId = useId();
  const panelRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const previousFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose();
      if (event.key === 'Tab') {
        const controls = Array.from(panelRef.current?.querySelectorAll<HTMLElement>('button, [href], [tabindex]:not([tabindex="-1"])') ?? []);
        if (controls.length === 0) return;
        const first = controls[0];
        const last = controls[controls.length - 1];
        if (!first || !last) return;
        if (event.shiftKey && (document.activeElement === first || document.activeElement === panelRef.current)) {
          event.preventDefault();
          last.focus();
        } else if (!event.shiftKey && document.activeElement === last) {
          event.preventDefault();
          first.focus();
        }
      }
    };
    document.addEventListener('keydown', onKey);
    const focusFrame = window.requestAnimationFrame(() => panelRef.current?.focus());
    return () => {
      window.cancelAnimationFrame(focusFrame);
      document.removeEventListener('keydown', onKey);
      previousFocus?.focus();
    };
  }, [onClose, open]);

  if (!open) return null;

  return createPortal(
    <div className="team-backdrop" role="presentation" onMouseDown={(event) => {
      if (event.target === event.currentTarget) onClose();
    }}>
      <section ref={panelRef} className="team-panel material-pop" role="dialog" aria-modal="true" aria-labelledby={titleId} tabIndex={-1}>
        <header className="team-head">
          <div>
            <p className="eyebrow">Noesis</p>
            <h2 id={titleId}>The team behind the system.</h2>
          </div>
          <button type="button" className="btn btn-icon" aria-label="Close team" onClick={onClose}><IconClose /></button>
        </header>
        <figure className="team-photo">
          <img src={teamPicture} alt="The Noesis team working together" />
        </figure>
        <div className="team-members" aria-label="Team members">
          {MEMBERS.map((member, index) => (
            <article className="team-member" key={member.name}>
              <span>{String(index + 1).padStart(2, '0')}</span>
              <strong>{member.name}</strong>
              <small>{member.role}</small>
            </article>
          ))}
        </div>
      </section>
    </div>,
    document.body,
  );
}

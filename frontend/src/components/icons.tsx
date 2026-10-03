import type { SVGProps } from 'react';

type IconProps = SVGProps<SVGSVGElement>;

function Base({ children, ...props }: IconProps) {
  return (
    <svg viewBox="0 0 16 16" width="16" height="16" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" {...props}>
      {children}
    </svg>
  );
}

export function IconShowcase(props: IconProps) {
  return <Base {...props}><circle cx="5" cy="8" r="2" /><circle cx="11" cy="5" r="2" /><circle cx="11" cy="11" r="2" /><path d="M7 8h2M9.6 6.2 7.4 7.4M9.6 9.8 7.4 8.6" /></Base>;
}

export function IconStream(props: IconProps) {
  return <Base {...props}><path d="M2.5 8h3l1.5-3 2 6 1.5-3h3" /></Base>;
}

export function IconPlay(props: IconProps) {
  return <Base {...props}><path d="M5 3.5v9l7-4.5-7-4.5z" fill="currentColor" stroke="none" /></Base>;
}

export function IconStop(props: IconProps) {
  return <Base {...props}><rect x="4.5" y="4.5" width="7" height="7" rx="1.2" fill="currentColor" stroke="none" /></Base>;
}

export function IconInspect(props: IconProps) {
  return <Base {...props}><circle cx="7" cy="7" r="3.2" /><path d="M9.4 9.4 13 13" /></Base>;
}

export function IconCompare(props: IconProps) {
  return <Base {...props}><path d="M3 4.5h4.5v7H3zM8.5 4.5H13v7H8.5z" /></Base>;
}

export function IconMode(props: IconProps) {
  return <Base {...props}><path d="M3 8h10M5 5.5 3 8l2 2.5M11 5.5 13 8l-2 2.5" /></Base>;
}

export function IconCommand(props: IconProps) {
  return <Base {...props}><rect x="2.5" y="3" width="11" height="10" rx="2" /><path d="M5.5 8h5M8 6.2v3.6" /></Base>;
}

export function IconTheme(props: IconProps) {
  return <Base {...props}><path d="M8 2.5v1.2M8 12.3v1.2M2.5 8h1.2M12.3 8h1.2M4.1 4.1l.9.9M11 11l.9.9M11.9 4.1 11 5M5 11l-.9.9" /><circle cx="8" cy="8" r="2.2" /></Base>;
}

export function IconClose(props: IconProps) {
  return <Base {...props}><path d="M4 4l8 8M12 4 4 12" /></Base>;
}

export function IconHome(props: IconProps) {
  return <Base {...props}><path d="M2.5 7.2 8 2.8l5.5 4.4v5.6a.7.7 0 0 1-.7.7H9.7V9.4H6.3v4.1H3.2a.7.7 0 0 1-.7-.7V7.2z" /></Base>;
}

export function IconEstimate(props: IconProps) {
  return <Base {...props}><path d="M3 12.5V9.8M6.3 12.5V7.2M9.7 12.5V4.8M13 12.5V2.8" /><path d="M2.5 13.5h11" /></Base>;
}

export function IconSecurity(props: IconProps) {
  return <Base {...props}><path d="M8 2.2 13 4v3.7c0 3-2 5-5 6.1-3-1.1-5-3.1-5-6.1V4l5-1.8z" /><path d="m5.8 8 1.4 1.4 3-3" /></Base>;
}

export function IconTeam(props: IconProps) {
  return <Base {...props}><circle cx="6" cy="5.5" r="2.1" /><circle cx="11.5" cy="6.3" r="1.55" /><path d="M2.6 13c.25-2.35 1.55-3.7 3.4-3.7s3.15 1.35 3.4 3.7M9.2 10c2.35-.55 3.8.55 4.2 2.7" /></Base>;
}

export function IconPlus(props: IconProps) {
  return <Base {...props}><path d="M8 3v10M3 8h10" /></Base>;
}

export function IconMic(props: IconProps) {
  return <Base {...props}><rect x="5.4" y="2.5" width="5.2" height="7.2" rx="2.6" /><path d="M3.7 8.2a4.3 4.3 0 0 0 8.6 0M8 12.5v1.2" /></Base>;
}

export function IconArrow(props: IconProps) {
  return <Base {...props}><path d="M3 8h9M9 4.8 12.2 8 9 11.2" /></Base>;
}

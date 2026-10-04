import {
  cloneElement,
  createContext,
  isValidElement,
  useContext,
  useEffect,
  useId,
  useLayoutEffect,
  useRef,
  useState,
  type FocusEvent as ReactFocusEvent,
  type MouseEvent as ReactMouseEvent,
  type MutableRefObject,
  type ReactElement,
  type ReactNode,
  type Ref,
} from 'react';
import { createPortal } from 'react-dom';

type TriggerProps = {
  ref?: Ref<HTMLElement>;
  onMouseEnter?: (event: ReactMouseEvent<HTMLElement>) => void;
  onMouseLeave?: (event: ReactMouseEvent<HTMLElement>) => void;
  onFocus?: (event: ReactFocusEvent<HTMLElement>) => void;
  onBlur?: (event: ReactFocusEvent<HTMLElement>) => void;
  'aria-describedby'?: string;
};

function mergeRefs<T>(...refs: Array<Ref<T> | undefined>) {
  return (node: T) => {
    for (const ref of refs) {
      if (typeof ref === 'function') ref(node);
      else if (ref) (ref as { current: T }).current = node;
    }
  };
}

interface TooltipApi {
  open: boolean;
  setOpen: (open: boolean) => void;
  anchorRef: React.RefObject<HTMLElement | null>;
  tipId: string;
  arm: () => void;
  disarm: () => void;
}

const TooltipContext = createContext<TooltipApi | null>(null);

export function Tooltip({ children }: { children: ReactNode }) {
  const [open, setOpen] = useState(false);
  const anchorRef = useRef<HTMLElement | null>(null);
  const timer = useRef<number | null>(null);
  const tipId = useId();

  const disarm = () => {
    if (timer.current !== null) window.clearTimeout(timer.current);
    timer.current = null;
    setOpen(false);
  };

  const arm = () => {
    if (timer.current !== null) window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => setOpen(true), 360);
  };

  useEffect(() => () => {
    if (timer.current !== null) window.clearTimeout(timer.current);
  }, []);

  useEffect(() => {
    if (!open) return;
    const onDown = (event: PointerEvent) => {
      if (anchorRef.current?.contains(event.target as Node)) return;
      disarm();
    };
    document.addEventListener('pointerdown', onDown);
    return () => document.removeEventListener('pointerdown', onDown);
  }, [open]);

  return (
    <TooltipContext.Provider value={{ open, setOpen, anchorRef, tipId, arm, disarm }}>
      {children}
    </TooltipContext.Provider>
  );
}

export function TooltipTrigger({ children }: { children: ReactElement<TriggerProps> }) {
  const ctx = useContext(TooltipContext);
  if (!ctx || !isValidElement(children)) return children;
  const childRef = children.props.ref;
  const triggerProps: TriggerProps = {
    ref: mergeRefs(childRef, ctx.anchorRef),
    onMouseEnter: (event: ReactMouseEvent<HTMLElement>) => {
      children.props.onMouseEnter?.(event);
      ctx.arm();
    },
    onMouseLeave: (event: ReactMouseEvent<HTMLElement>) => {
      children.props.onMouseLeave?.(event);
      ctx.disarm();
    },
    onFocus: (event: ReactFocusEvent<HTMLElement>) => {
      children.props.onFocus?.(event);
      ctx.setOpen(true);
    },
    onBlur: (event: ReactFocusEvent<HTMLElement>) => {
      children.props.onBlur?.(event);
      ctx.disarm();
    },
  };
  if (ctx.open) triggerProps['aria-describedby'] = ctx.tipId;
  return cloneElement(children, triggerProps);
}

export function TooltipContent({ children, shortcut }: { children: ReactNode; shortcut?: string }) {
  const ctx = useContext(TooltipContext);
  const tipRef = useRef<HTMLDivElement>(null);
  const [box, setBox] = useState<{ top: number; left: number } | null>(null);
  const open = ctx?.open ?? false;

  useLayoutEffect(() => {
    if (!open) return;
    const place = () => {
      const anchor = ctx?.anchorRef.current;
      const tip = tipRef.current;
      if (!anchor || !tip) return;
      const rect = anchor.getBoundingClientRect();
      const width = tip.offsetWidth;
      const height = tip.offsetHeight;
      const left = Math.max(8, Math.min(rect.left + rect.width / 2 - width / 2, window.innerWidth - width - 8));
      const top = rect.top > height + 16 ? rect.top - height - 8 : rect.bottom + 8;
      setBox((prev) => (prev && prev.top === top && prev.left === left ? prev : { top, left }));
    };
    place();
    window.addEventListener('scroll', place, true);
    window.addEventListener('resize', place);
    return () => {
      window.removeEventListener('scroll', place, true);
      window.removeEventListener('resize', place);
    };
  }, [open, ctx, children, shortcut]);

  if (!ctx?.open) return null;
  return createPortal(
    <div
      ref={tipRef}
      id={ctx.tipId}
      role="tooltip"
      className="tooltip material-pop"
      style={{ top: box?.top ?? 0, left: box?.left ?? 0, visibility: box ? 'visible' : 'hidden' }}
    >
      <span>{children}</span>
      {shortcut && <kbd>{shortcut}</kbd>}
    </div>,
    document.body,
  );
}

interface PopoverApi {
  open: boolean;
  setOpen: (open: boolean) => void;
  rootRef: MutableRefObject<HTMLDivElement | null>;
  triggerRef: MutableRefObject<HTMLButtonElement | null>;
  panelRef: MutableRefObject<HTMLDivElement | null>;
}

const PopoverContext = createContext<PopoverApi | null>(null);

export function Popover({ children }: { children: ReactNode }) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement | null>(null);
  const triggerRef = useRef<HTMLButtonElement | null>(null);
  const panelRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!open) return;
    const onPointer = (event: MouseEvent) => {
      const target = event.target as Node;
      if (rootRef.current?.contains(target) || panelRef.current?.contains(target)) return;
      setOpen(false);
    };
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setOpen(false);
    };
    document.addEventListener('mousedown', onPointer);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('mousedown', onPointer);
      document.removeEventListener('keydown', onKey);
    };
  }, [open]);

  return (
    <PopoverContext.Provider value={{ open, setOpen, rootRef, triggerRef, panelRef }}>
      <div className="popover-root" ref={rootRef}>{children}</div>
    </PopoverContext.Provider>
  );
}

export function PopoverTrigger({
  children,
  label,
  className = 'btn btn-icon',
}: {
  children: ReactNode;
  label: string;
  className?: string;
}) {
  const ctx = useContext(PopoverContext);
  if (!ctx) return null;
  return (
    <button ref={ctx.triggerRef} type="button" className={className} aria-label={label} aria-expanded={ctx.open} aria-haspopup="dialog" onClick={() => ctx.setOpen(!ctx.open)}>
      {children}
    </button>
  );
}

export function PopoverContent({ children, title }: { children: ReactNode; title: string }) {
  const ctx = useContext(PopoverContext);
  const [box, setBox] = useState<{ top: number; left: number } | null>(null);
  const open = ctx?.open ?? false;

  useLayoutEffect(() => {
    if (!open) return;
    const place = () => {
      const anchor = ctx?.triggerRef.current;
      const panel = ctx?.panelRef.current;
      if (!anchor || !panel) return;
      const rect = anchor.getBoundingClientRect();
      const width = panel.offsetWidth;
      const height = panel.offsetHeight;
      let nextLeft = rect.left;
      if (nextLeft + width > window.innerWidth - 8) nextLeft = rect.right - width;
      nextLeft = Math.max(8, Math.min(nextLeft, window.innerWidth - width - 8));
      let nextTop = rect.bottom + 8;
      if (nextTop + height > window.innerHeight - 8) nextTop = Math.max(8, rect.top - height - 8);
      setBox((prev) => (prev && prev.top === nextTop && prev.left === nextLeft ? prev : { top: nextTop, left: nextLeft }));
    };
    place();
    ctx?.panelRef.current?.focus();
    window.addEventListener('resize', place);
    window.addEventListener('scroll', place, true);
    return () => {
      window.removeEventListener('resize', place);
      window.removeEventListener('scroll', place, true);
    };
  }, [open, ctx, children, title]);

  if (!ctx?.open) return null;
  return createPortal(
    <div
      ref={ctx.panelRef}
      className="popover material-pop"
      role="dialog"
      aria-label={title}
      tabIndex={-1}
      style={{ top: box?.top ?? 0, left: box?.left ?? 0, visibility: box ? 'visible' : 'hidden' }}
    >
      <p className="eyebrow">{title}</p>
      {children}
    </div>,
    document.body,
  );
}

export interface MenuItem {
  id: string;
  label: string;
  onSelect: () => void;
}

export function ContextMenu({
  point,
  items,
  onClose,
}: {
  point: { x: number; y: number } | null;
  items: MenuItem[];
  onClose: () => void;
}) {
  const ref = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!point) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose();
      if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
        event.preventDefault();
        const buttons = ref.current?.querySelectorAll<HTMLButtonElement>('button') ?? [];
        const list = Array.from(buttons);
        const index = list.indexOf(document.activeElement as HTMLButtonElement);
        const next = event.key === 'ArrowDown' ? index + 1 : index - 1;
        list[(next + list.length) % list.length]?.focus();
      }
    };
    const onPointer = (event: MouseEvent) => {
      if (!ref.current?.contains(event.target as Node)) onClose();
    };
    document.addEventListener('keydown', onKey);
    document.addEventListener('mousedown', onPointer);
    ref.current?.querySelector('button')?.focus();
    return () => {
      document.removeEventListener('keydown', onKey);
      document.removeEventListener('mousedown', onPointer);
    };
  }, [point, onClose]);

  if (!point) return null;
  const left = Math.min(point.x, window.innerWidth - 196);
  const top = Math.min(point.y, window.innerHeight - 40 - items.length * 32);
  return createPortal(
    <div ref={ref} className="context-menu material-pop" role="menu" style={{ top, left }}>
      {items.map((item) => (
        <button
          key={item.id}
          type="button"
          role="menuitem"
          onClick={() => {
            item.onSelect();
            onClose();
          }}
        >
          {item.label}
        </button>
      ))}
    </div>,
    document.body,
  );
}

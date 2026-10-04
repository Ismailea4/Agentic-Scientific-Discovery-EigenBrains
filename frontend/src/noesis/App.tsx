import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState, type CSSProperties, type ReactNode } from 'react';
import type { HealthStatus } from './api/types';
import { CommandPalette, type Command } from './components/command';
import { CommandSurface } from './components/CommandSurface';
import { IconClose, IconCommand, IconCompare, IconEstimate, IconHome, IconInspect, IconSecurity, IconShowcase, IconStream, IconTeam, IconTheme } from './components/icons';
import { Popover, PopoverContent, PopoverTrigger, Tooltip, TooltipContent, TooltipTrigger } from './components/overlay';
import { ShellProvider, type ThemeChoice } from './components/shell';
import { TeamPanel } from './components/TeamPanel';
import { StatusCapsule } from './components/ui';
import { AgentsExperience } from './experiences/AgentsExperience';
import { EstimationExperience } from './experiences/EstimationExperience';
import { SecurityExperience } from './experiences/SecurityExperience';
import { TraceExperience } from './experiences/TraceExperience';
import { useGet, type GetState } from './hooks/useGet';
import { useHashView, type AppView } from './hooks/useHashView';
import { useQuietMotion } from './hooks/useQuietMotion';
import { Home } from './views/Home';
import { LabBar } from './lab/LabBar';
import { DiscoveryStory, SAMPLE_STORY } from './lab/DiscoveryStory';
import { LabProvider, useLab } from './lab/LabContext';
import { LiveApproval, LiveDiscovery, LiveHypotheses, LiveRecord } from './lab/LiveViews';
import noesisLogo from '../assets/logo_noesis.png';

const NAV: { id: AppView; label: string; icon: typeof IconHome; reveal: number }[] = [
  { id: 'home', label: 'Home', icon: IconHome, reveal: 0 },
  { id: 'discovery', label: 'Discovery Loop', icon: IconShowcase, reveal: 1 },
  { id: 'hypotheses', label: 'Hypotheses', icon: IconEstimate, reveal: 2 },
  { id: 'approval', label: 'Human Approval Gate', icon: IconSecurity, reveal: 3 },
  { id: 'record', label: 'Research Record', icon: IconStream, reveal: 4 },
];

function readTheme(): ThemeChoice {
  if (typeof window === 'undefined') return 'dark';
  const stored = window.localStorage.getItem('eb-theme');
  return stored === 'light' || stored === 'dark' || stored === 'system' ? stored : 'dark';
}

export default function App() {
  return <LabProvider><AppShell /></LabProvider>;
}

function AppShell() {
  const lab = useLab();
  const live = lab.status === 'connected' && lab.sourceId !== null;
  const [view, navigate] = useHashView();
  const quietMotion = useQuietMotion();
  const health = useGet<HealthStatus>('/health');
  const [theme, setTheme] = useState<ThemeChoice>('dark');
  const [inspector, setInspector] = useState<ReactNode>(null);
  const [inspectorOpen, setInspectorOpen] = useState(false);
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [teamOpen, setTeamOpen] = useState(false);
  const [storyChapter, setStoryChapter] = useState(0);
  const [materialization, setMaterialization] = useState({ id: 0, originY: 96, active: false });
  const homeScroll = useRef(0);
  const isStory = view === 'home' && !quietMotion;

  useEffect(() => {
    setTheme(readTheme());
  }, []);

  useEffect(() => {
    if (theme === 'system') delete document.documentElement.dataset['theme'];
    else document.documentElement.dataset['theme'] = theme;
    window.localStorage.setItem('eb-theme', theme);
  }, [theme]);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'k') {
        event.preventDefault();
        setPaletteOpen((open) => !open);
      }
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'i') {
        event.preventDefault();
        setInspectorOpen((open) => !open);
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  const cycleTheme = useCallback(() => {
    setTheme((current) => (current === 'dark' ? 'light' : 'dark'));
  }, []);

  const closeTeam = useCallback(() => setTeamOpen(false), []);

  const go = useCallback((next: AppView, source?: HTMLElement) => {
    if (next === view) return;
    if (view === 'home') homeScroll.current = window.scrollY;
    const sourceBox = source?.getBoundingClientRect();
    setMaterialization((current) => ({
      id: current.id + 1,
      originY: sourceBox ? Math.max(20, sourceBox.top + sourceBox.height / 2 - 52) : 96,
      active: true,
    }));
    navigate(next);
    setInspectorOpen(false);
    setInspector(null);
  }, [navigate, view]);

  useLayoutEffect(() => {
    window.scrollTo({ top: view === 'home' ? homeScroll.current : 0, behavior: 'auto' });
  }, [view]);

  const commands = useMemo<Command[]>(() => [
    ...NAV.map((item) => ({ id: item.id, label: `Open ${item.label}`, run: () => go(item.id) })),
    { id: 'inspect-selected', label: 'Inspect selected', run: () => setInspectorOpen(true) },
    { id: 'inspect', label: 'Toggle inspector', hint: 'Ctrl I', run: () => setInspectorOpen((open) => !open) },
    { id: 'theme', label: 'Toggle theme', run: cycleTheme },
  ], [cycleTheme, go]);

  const shell = useMemo(() => ({
    view,
    navigate: go,
    inspectorOpen,
    setInspectorOpen,
    setInspector,
    theme,
    setTheme,
  }), [go, inspectorOpen, theme, view]);

  const showCommandSurface = view === 'home' && (quietMotion || storyChapter >= 5);

  return (
    <ShellProvider value={shell}>
      <div className={isStory ? 'app-frame is-story' : 'app-frame'} data-chapter={isStory ? storyChapter : undefined}>
        <a className="skip" href="#workspace">Skip to workspace</a>
        <aside className="sidebar material-side">
          <div className="brand"><span className="brand-mark"><img src={noesisLogo} alt="" /></span><strong>Noesis</strong></div>
          <nav className="side-nav" aria-label="Primary">
            {NAV.map((item) => {
              const Icon = item.icon;
              const soon = isStory && storyChapter >= item.reveal && item.id !== 'home';
              return (
                <Tooltip key={item.id}>
                  <TooltipTrigger>
                    <button type="button" className={soon ? 'side-link is-soon' : 'side-link'} aria-current={view === item.id ? 'page' : undefined} onClick={(event) => go(item.id, event.currentTarget)}>
                      <Icon /><span>{item.label}</span>
                    </button>
                  </TooltipTrigger>
                  <TooltipContent>{item.label}</TooltipContent>
                </Tooltip>
              );
            })}
          </nav>
          <div className="sidebar-footer">
            <button type="button" className="side-link team-trigger" aria-expanded={teamOpen} aria-haspopup="dialog" onClick={() => setTeamOpen(true)}>
              <IconTeam /><span>Team</span>
            </button>
          </div>
        </aside>
        <div className="workspace-col">
          <header className="toolbar material-bar">
            <h1 className="toolbar-title">{NAV.find((item) => item.id === view)?.label}</h1>
            <div className="toolbar-actions">
              <Tooltip><TooltipTrigger><button type="button" className="btn btn-icon" aria-label="Commands" onClick={() => setPaletteOpen(true)}><IconCommand /></button></TooltipTrigger><TooltipContent shortcut="Ctrl K">Commands</TooltipContent></Tooltip>
              <Tooltip><TooltipTrigger><button type="button" className="btn btn-icon" aria-label="Toggle inspector" aria-pressed={inspectorOpen} onClick={() => setInspectorOpen((open) => !open)}><IconInspect /></button></TooltipTrigger><TooltipContent shortcut="Ctrl I">Inspect</TooltipContent></Tooltip>
              <Popover><PopoverTrigger label="Compare"><IconCompare /></PopoverTrigger><PopoverContent title="Compare"><p className="quiet">Pick two candidate hypotheses to compare evidence, confidence, and risk.</p></PopoverContent></Popover>
              <Tooltip><TooltipTrigger><button type="button" className="btn btn-icon" aria-label="Toggle theme" onClick={cycleTheme}><IconTheme /></button></TooltipTrigger><TooltipContent>Theme</TooltipContent></Tooltip>
              <HealthCapsule health={health} />
            </div>
          </header>
          <div className={inspectorOpen ? 'stage inspector-open' : 'stage'}>
            <div
              key={`${view}-${materialization.id}`}
              className={`${view === 'home' ? 'stage-main home-stage' : 'stage-main workspace-stage'}${materialization.active ? ' is-unfolding' : ''}`}
              style={{ '--unfold-origin-y': `${materialization.originY}px` } as CSSProperties}
              onAnimationEnd={(event) => {
                if (event.animationName === 'dock-unfold-right') {
                  setMaterialization((current) => ({ ...current, active: false }));
                }
              }}
            >
              {view === 'home' ? <Home quiet={quietMotion} chapter={storyChapter} onChapterChange={setStoryChapter} /> : null}
              {view === 'discovery' ? <main id="workspace" className="stage-stack"><LabBar />{live ? <LiveDiscovery /> : <><DiscoveryStory state={SAMPLE_STORY.state} activity={SAMPLE_STORY.activity} kind="sample" sampleExperiment={SAMPLE_STORY.experiment} /><AgentsExperience mode="workspace" /></>}</main> : null}
              {view === 'hypotheses' ? <main id="workspace" className="stage-stack"><LabBar />{live ? <LiveHypotheses /> : <EstimationExperience mode="workspace" />}</main> : null}
              {view === 'approval' ? <main id="workspace" className="stage-stack"><LabBar />{live ? <LiveApproval /> : <SecurityExperience mode="workspace" />}</main> : null}
              {view === 'record' ? <main id="workspace" className="stage-stack"><LabBar />{live ? <LiveRecord /> : <TraceExperience mode="workspace" />}</main> : null}
            </div>
            <aside className={inspectorOpen ? 'inspector-dock is-open material-sheet' : 'inspector-dock material-sheet'} aria-label="Scientific record inspector" aria-hidden={!inspectorOpen}>
              <button type="button" className="sheet-grab" aria-label="Close inspector" onClick={() => setInspectorOpen(false)} />
              <div className="inspector-head"><p className="eyebrow">Scientific record</p><button type="button" className="btn btn-icon" aria-label="Close inspector" onClick={() => setInspectorOpen(false)}><IconClose /></button></div>
              <div className="inspector-scroll">{inspector ?? <p className="quiet">Nothing selected</p>}</div>
            </aside>
          </div>
        </div>
        {showCommandSurface ? <CommandSurface docked /> : null}
        <TeamPanel open={teamOpen} onClose={closeTeam} />
        <CommandPalette open={paletteOpen} commands={commands} onClose={() => setPaletteOpen(false)} />
      </div>
    </ShellProvider>
  );
}

function HealthCapsule({ health }: { health: GetState<HealthStatus> }) {
  if (health.loading) return <StatusCapsule tone="idle">Checking</StatusCapsule>;
  if (health.error || !health.data) return <StatusCapsule tone="bad">Core API offline</StatusCapsule>;
  if (health.data.status === 'ok') return <StatusCapsule tone="ok">Ready</StatusCapsule>;
  return <StatusCapsule tone="warn">{health.data.status}</StatusCapsule>;
}

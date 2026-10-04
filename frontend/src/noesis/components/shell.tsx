import { createContext, useContext, type ReactNode } from 'react';
import type { AppView } from '../hooks/useHashView';

export type ThemeChoice = 'system' | 'light' | 'dark';

export interface ShellApi {
  view: AppView;
  navigate: (view: AppView) => void;
  inspectorOpen: boolean;
  setInspectorOpen: (open: boolean) => void;
  setInspector: (node: ReactNode) => void;
  theme: ThemeChoice;
  setTheme: (theme: ThemeChoice) => void;
}

const ShellContext = createContext<ShellApi | null>(null);

export function ShellProvider({ value, children }: { value: ShellApi; children: ReactNode }) {
  return <ShellContext.Provider value={value}>{children}</ShellContext.Provider>;
}

export function useShell(): ShellApi {
  const value = useContext(ShellContext);
  if (!value) throw new Error('useShell must be used inside the application shell');
  return value;
}

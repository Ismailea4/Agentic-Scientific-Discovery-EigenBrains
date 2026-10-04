import { useCallback, useEffect, useState } from 'react';

const KEY = 'noesis-sound-on';
let ctx: AudioContext | null = null;
const listeners = new Set<(on: boolean) => void>();
let enabled = false;

function audio(): AudioContext | null {
  if (typeof window === 'undefined') return null;
  if (!ctx) {
    const C = window.AudioContext ?? (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
    if (!C) return null;
    ctx = new C();
  }
  return ctx;
}

function tone(freq: number, dur: number, type: OscillatorType, gain: number, delay = 0) {
  const a = audio();
  if (!a || !enabled) return;
  const t = a.currentTime + delay;
  const o = a.createOscillator();
  const g = a.createGain();
  o.type = type;
  o.frequency.setValueAtTime(freq, t);
  g.gain.setValueAtTime(0, t);
  g.gain.linearRampToValueAtTime(gain, t + 0.01);
  g.gain.exponentialRampToValueAtTime(0.0001, t + dur);
  o.connect(g).connect(a.destination);
  o.start(t);
  o.stop(t + dur + 0.02);
}

export const sounds = {
  tick: () => tone(1320, 0.06, 'triangle', 0.05),
  hum: () => { tone(110, 0.9, 'sine', 0.035); tone(165, 0.9, 'sine', 0.02); },
  chime: () => { tone(880, 0.6, 'sine', 0.06); tone(1318.5, 0.8, 'sine', 0.045, 0.12); },
};

/** Sound is off by default; the toggle stores the choice. */
export function useSound() {
  const [on, setOn] = useState(false);
  useEffect(() => {
    enabled = localStorage.getItem(KEY) === '1';
    setOn(enabled);
    listeners.add(setOn);
    return () => { listeners.delete(setOn); };
  }, []);
  const toggle = useCallback(() => {
    enabled = !enabled;
    localStorage.setItem(KEY, enabled ? '1' : '0');
    if (enabled) { void audio()?.resume(); sounds.tick(); }
    listeners.forEach((l) => l(enabled));
  }, []);
  return { on, toggle, ...sounds };
}

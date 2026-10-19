import { useCallback, useEffect, useRef, useState } from 'react';

export function useAlertTone() {
  const [playing, setPlaying] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const active = useRef<AudioContext | null>(null);
  const starting = useRef(false);
  const mounted = useRef(true);
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
      const context = active.current;
      active.current = null;
      void context?.close().catch(() => {});
    };
  }, []);
  const play = useCallback(async () => {
    if (starting.current || active.current) return false;
    starting.current = true;
    setError(null);
    let context: AudioContext | null = null;
    try {
      const Constructor = window.AudioContext || (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
      if (!Constructor) throw new Error('This browser does not support the test tone.');
      context = new Constructor();
      active.current = context;
      await context.resume();
      if (!mounted.current || active.current !== context) return false;
      const oscillator = context.createOscillator();
      const gain = context.createGain();
      oscillator.type = 'sawtooth';
      oscillator.frequency.setValueAtTime(880, context.currentTime);
      oscillator.frequency.exponentialRampToValueAtTime(440, context.currentTime + .35);
      gain.gain.setValueAtTime(.12, context.currentTime);
      gain.gain.exponentialRampToValueAtTime(.01, context.currentTime + .35);
      oscillator.connect(gain);
      gain.connect(context.destination);
      oscillator.onended = () => {
        if (active.current === context) {
          active.current = null;
          if (mounted.current) setPlaying(false);
        }
        void context?.close().catch(() => {});
      };
      oscillator.start();
      oscillator.stop(context.currentTime + .35);
      setPlaying(true);
      return true;
    } catch (err) {
      active.current = null;
      if (context) void context.close().catch(() => {});
      if (mounted.current) {
        setPlaying(false);
        setError(err instanceof Error ? err.message : 'The test tone could not play. Check browser sound settings.');
      }
      return false;
    } finally {
      starting.current = false;
    }
  }, []);
  return { playing, error, play };
}

import { useEffect, useState, type RefObject } from 'react';
import { inferSingleImage } from '../services/api.ts';
import type { ModelClass } from '../constants/classes.ts';
import type { SingleImageInferenceResponse } from '../types/sightline.ts';

export interface FramePrediction {
  response: SingleImageInferenceResponse;
  image: Blob;
  sourceTime: number;
  source: string;
  targetKey: string;
}

/** Samples the visible source with one request at a time; never saves or dispatches. */
export function useFrameDetection(
  videoRef: RefObject<HTMLVideoElement | null>,
  source: string | null,
  enabled: boolean,
  live: boolean,
  targetKey: string,
) {
  const [prediction, setPrediction] = useState<FramePrediction | null>(null);
  const [status, setStatus] = useState<'idle' | 'waiting' | 'analyzing' | 'ready' | 'error'>('idle');
  const [error, setError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    setPrediction(null);
    setError(null);
    if (!enabled || !source || !targetKey) {
      setStatus('idle');
      return;
    }
    const activeSource = source;
    let cancelled = false;
    let timer: number | undefined;
    let lastFrameTime = -1;
    let capturedAt = 0;
    let seekVersion = 0;
    const controller = new AbortController();
    const targets = targetKey.split(',') as ModelClass[];
    const canvas = document.createElement('canvas');
    const schedule = (delay: number) => {
      if (!cancelled) timer = window.setTimeout(analyze, delay);
    };
    const invalidate = () => {
      seekVersion += 1;
      lastFrameTime = -1;
      setPrediction(null);
    };
    const video = videoRef.current;
    video?.addEventListener('seeking', invalidate);

    async function analyze() {
      const current = videoRef.current;
      if (cancelled) return;
      if (!current || current.readyState < 2 || !current.videoWidth || !current.videoHeight || current.seeking || document.hidden) {
        schedule(200);
        return;
      }
      // Re-analyze a paused video after seeking, but don't upload the same still repeatedly.
      if (!live && Math.abs(current.currentTime - lastFrameTime) < 0.15) {
        schedule(200);
        return;
      }
      const sourceTime = current.currentTime;
      const capturedSeekVersion = seekVersion;
      const requestStartedAt = performance.now();
      capturedAt = requestStartedAt;
      canvas.width = Math.min(1280, current.videoWidth);
      canvas.height = Math.round(current.videoHeight * canvas.width / current.videoWidth);
      const context = canvas.getContext('2d');
      if (!context) {
        setError('This browser could not capture a video frame. Try another browser.');
        setStatus('error');
        return;
      }
      try {
        context.drawImage(current, 0, 0, canvas.width, canvas.height);
        const blob = await new Promise<Blob | null>(resolve => canvas.toBlob(resolve, 'image/jpeg', 0.9));
        if (cancelled) return;
        if (!blob) throw new Error('Unable to capture a frame for analysis.');
        setStatus('analyzing');
        const response = await inferSingleImage(blob, targets, 0.25, { signal: controller.signal, timeoutMs: 10000 });
        if (cancelled) return;
        // A seek or loop may complete while the API is processing. Discard that response.
        if (capturedSeekVersion === seekVersion && (live || Math.abs(current.currentTime - sourceTime) < 1.25)) {
          lastFrameTime = sourceTime;
          setPrediction({ response, image: blob, sourceTime, source: activeSource, targetKey });
          setStatus('ready');
        } else {
          setPrediction(null);
          setStatus('waiting');
        }
        schedule(Math.max(80, 700 - (performance.now() - requestStartedAt)));
      } catch (err) {
        if (cancelled) return;
        setPrediction(null);
        setStatus('error');
        setError(err instanceof Error ? err.message : 'Frame analysis failed. Check the backend and retry.');
      }
    }

    // Remove stale boxes during outages, pauses, loops or source-time jumps.
    const expiry = window.setInterval(() => {
      if (cancelled) return;
      setPrediction(previous => {
        if (!previous) return previous;
        const current = videoRef.current;
        if (!current || (live && performance.now() - capturedAt > 1800)
          || (!live && Math.abs(current.currentTime - previous.sourceTime) >= 1.25)) return null;
        return previous;
      });
    }, 200);
    setStatus('waiting');
    schedule(0);
    return () => {
      cancelled = true;
      controller.abort();
      window.clearTimeout(timer);
      window.clearInterval(expiry);
      video?.removeEventListener('seeking', invalidate);
    };
  }, [videoRef, source, enabled, live, targetKey, attempt]);

  const visiblePrediction = enabled && prediction?.source === source && prediction.targetKey === targetKey ? prediction : null;
  return { prediction: visiblePrediction, status, error, retry: () => setAttempt(previous => previous + 1) };
}

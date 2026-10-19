import { useCallback, useEffect, useRef, useState, type RefObject } from 'react';

function cameraMessage(error: unknown): string {
  const name = error instanceof DOMException ? error.name : '';
  if (name === 'NotAllowedError' || name === 'SecurityError') {
    return 'This browser or macOS denied the camera request. Allow Camera for this site and for your browser in System Settings → Privacy & Security → Camera, then retry. If you are using an in-app browser, open http://localhost:8000 in Chrome or Safari.';
  }
  if (name === 'NotFoundError') return 'No camera was found. Connect or enable a camera, then try again.';
  if (name === 'NotReadableError' || name === 'AbortError') {
    return 'The camera could not start. Close other apps using it, check system camera access, then try again.';
  }
  return error instanceof Error ? error.message : 'Unable to open the camera. Please try again.';
}

/** Owns camera tracks independently of file URLs and releases cancelled requests. */
export function useCameraPreview(videoRef: RefObject<HTMLVideoElement | null>) {
  const [stream, setStream] = useState<MediaStream | null>(null);
  const [status, setStatus] = useState<'idle' | 'requesting' | 'active' | 'error'>('idle');
  const [error, setError] = useState<string | null>(null);
  const [previewBlocked, setPreviewBlocked] = useState(false);
  const generation = useRef(0);
  const mounted = useRef(true);
  const requesting = useRef(false);
  const currentStream = useRef<MediaStream | null>(null);
  const removeListeners = useRef<(() => void) | null>(null);

  const release = useCallback(() => {
    generation.current += 1;
    requesting.current = false;
    removeListeners.current?.();
    removeListeners.current = null;
    const previous = currentStream.current;
    currentStream.current = null;
    previous?.getTracks().forEach(track => track.stop());
    if (videoRef.current?.srcObject === previous) videoRef.current.srcObject = null;
  }, [videoRef]);

  const stop = useCallback(() => {
    release();
    setStream(null);
    setStatus('idle');
    setError(null);
    setPreviewBlocked(false);
  }, [release]);

  const start = useCallback(async () => {
    if (requesting.current || currentStream.current) return;
    const request = ++generation.current;
    requesting.current = true;
    setStatus('requesting');
    setError(null);
    setPreviewBlocked(false);
    try {
      if (!window.isSecureContext) {
        throw new Error('Camera access requires HTTPS or localhost. Open this app at http://localhost:8000 on this computer, or use HTTPS.');
      }
      if (!navigator.mediaDevices?.getUserMedia) {
        throw new Error('This browser does not support camera access. Open the app in an up-to-date Chrome, Edge, Firefox, or Safari browser.');
      }
      const policyDocument = document as Document & {
        permissionsPolicy?: { allowsFeature: (feature: string) => boolean };
        featurePolicy?: { allowsFeature: (feature: string) => boolean };
      };
      const policy = policyDocument.permissionsPolicy || policyDocument.featurePolicy;
      if (policy && !policy.allowsFeature('camera')) {
        throw new Error('This embedded browser does not allow camera access. Open http://localhost:8000 in Chrome or Safari and select Live Camera.');
      }
      let next: MediaStream;
      try {
        next = await navigator.mediaDevices.getUserMedia({
          video: { width: { ideal: 1280 }, height: { ideal: 720 }, facingMode: { ideal: 'user' } },
          audio: false,
        });
      } catch (err) {
        if (!(err instanceof DOMException) || err.name !== 'OverconstrainedError' || request !== generation.current) throw err;
        next = await navigator.mediaDevices.getUserMedia({ video: true, audio: false });
      }
      if (!mounted.current || request !== generation.current) {
        next.getTracks().forEach(track => track.stop());
        return;
      }
      currentStream.current = next;
      requesting.current = false;
      const ended = () => {
        release();
        setStream(null);
        setStatus('error');
        setError('The camera disconnected or access ended. Reconnect it and try Live Camera again.');
      };
      next.getVideoTracks().forEach(track => track.addEventListener('ended', ended));
      removeListeners.current = () => next.getVideoTracks().forEach(track => track.removeEventListener('ended', ended));
      setStream(next);
      setStatus('active');
    } catch (err) {
      if (!mounted.current || request !== generation.current) return;
      requesting.current = false;
      setStatus('error');
      setError(cameraMessage(err));
    }
  }, [release]);

  const resumePreview = useCallback(async () => {
    const video = videoRef.current;
    const source = currentStream.current;
    if (!video || !source) return;
    // Set DOM properties explicitly as well as JSX attributes for WebKit autoplay.
    video.muted = true;
    video.defaultMuted = true;
    video.playsInline = true;
    video.srcObject = source;
    try {
      await video.play();
      if (!mounted.current || currentStream.current !== source) return;
      setPreviewBlocked(false);
      setError(null);
    } catch {
      if (!mounted.current || currentStream.current !== source) return;
      // Camera permission has already succeeded; don't stop the stream or report
      // a playback restriction as denied camera access.
      setPreviewBlocked(true);
      setError('The camera is connected, but preview playback was paused by the browser. Select Resume Camera Preview.');
    }
  }, [videoRef]);

  // The conditional <video> exists only after React commits the active state.
  useEffect(() => {
    const video = videoRef.current;
    if (!video || !stream) return;
    void resumePreview();
    return () => {
      if (video.srcObject === stream) video.srcObject = null;
    };
  }, [stream, videoRef, resumePreview]);

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
      release();
    };
  }, [release]);

  return { start, stop, status, error, previewBlocked, resumePreview, active: status === 'active', pending: status === 'requesting' };
}

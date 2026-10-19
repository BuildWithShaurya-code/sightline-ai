import type { Detection } from '../types/sightline.ts';
import type { FramePrediction } from '../hooks/useFrameDetection.ts';

export const MASK_ALERT_MIN_CONFIDENCE = .60;
/** Alert threshold is separate from the 25% inference/evidence display threshold. */
export function maskAlertConfidence(detections:Detection[]):number|null {
  const valid=detections.filter(d=>d.classId==='mask'&&Number.isFinite(d.confidence)&&d.confidence>=MASK_ALERT_MIN_CONFIDENCE&&d.confidence<=1);
  return valid.length?Math.max(...valid.map(d=>d.confidence)):null;
}

/** One warning per mask episode; a person alone never triggers a siren. */
export class MaskAlertGate {
  private clear = 0;
  private active = false;
  private lastAlert = -Infinity;
  observe(prediction: FramePrediction | null, now: number): number | null {
    if (!prediction) return null;
    return this.observeDetections(prediction.response.detections, now);
  }
  observeDetections(detections: Detection[], now: number): number | null {
    const confidence = maskAlertConfidence(detections);
    if (confidence === null) {
      if (++this.clear >= 3) this.active = false;
      return null;
    }
    this.clear = 0;
    if (!this.active && now - this.lastAlert >= 30000) {
      this.active = true; this.lastAlert = now; return confidence;
    }
    return null;
  }
}

let context: AudioContext | null = null;
let oscillator: OscillatorNode | null = null;
let gain: GainNode | null = null;
let timer: ReturnType<typeof setTimeout> | undefined;
export type AudioStatus = { ready: boolean; playing: boolean; error: string | null };
let status: AudioStatus = {ready:false, playing:false, error:null};
const listeners = new Set<(s: AudioStatus) => void>();
const update = (patch: Partial<AudioStatus>) => {status = {...status,...patch}; listeners.forEach(fn => fn(status));};
export const getSirenStatus = () => status;
export const subscribeSiren = (fn: (s: AudioStatus) => void) => {listeners.add(fn); return () => {listeners.delete(fn);};};

/** Must be called synchronously from a click/key event to satisfy browser autoplay rules. */
export async function enableSiren(): Promise<boolean> {
  try {
    const Constructor = window.AudioContext || (window as unknown as {webkitAudioContext?: typeof AudioContext}).webkitAudioContext;
    if (!Constructor) throw new Error('Siren audio is unavailable in this browser.');
    if (!context || context.state === 'closed') {
      context = new Constructor();
      context.onstatechange = () => update({ready:context?.state === 'running'});
    }
    if (context.state === 'running') { if (!status.ready || status.error) update({ready:true,error:null}); return true; }
    // Do not await a resume blocked by policy indefinitely.
    const resumed = context.resume();
    await Promise.race([resumed, new Promise<void>(resolve => setTimeout(resolve, 700))]);
    if ((context.state as AudioContextState) !== 'running') throw new Error('Select Enable siren to allow alert sound in this browser.');
    update({ready:true,error:null});
    return true;
  } catch (e) {
    update({ready:false,error:e instanceof Error ? e.message : 'Alert sound is blocked.'});
    return false;
  }
}
export function stopSiren() {
  clearTimeout(timer);
  const prior = oscillator; oscillator = null;
  if (prior) { prior.onended = null; try {prior.stop();} catch {} prior.disconnect(); }
  gain?.disconnect(); gain = null;
  update({playing:false});
}
export function playMaskSiren(): boolean {
  stopSiren();
  if (!context || context.state !== 'running') {
    update({ready:false,error:'Sound is blocked. Select Enable siren, then Play siren for this alert.'});
    return false;
  }
  try {
    const current = context;
    oscillator = current.createOscillator(); gain = current.createGain();
    oscillator.type = 'triangle';
    const now = current.currentTime;
    for (let i=0;i<8;i++) {
      oscillator.frequency.setValueAtTime(540, now+i*.65);
      oscillator.frequency.linearRampToValueAtTime(1080, now+i*.65+.30);
      oscillator.frequency.linearRampToValueAtTime(540, now+i*.65+.60);
    }
    gain.gain.setValueAtTime(0,now);
    gain.gain.linearRampToValueAtTime(.16,now+.04);
    gain.gain.setValueAtTime(.16,now+5.1);
    gain.gain.linearRampToValueAtTime(0,now+5.25);
    oscillator.connect(gain); gain.connect(current.destination);
    oscillator.start(); oscillator.stop(now+5.3);
    oscillator.onended = stopSiren;
    timer = setTimeout(stopSiren,5500);
    update({ready:true,playing:true,error:null});
    return true;
  } catch (e) {
    stopSiren(); update({error:e instanceof Error ? e.message : 'Siren could not start.'}); return false;
  }
}

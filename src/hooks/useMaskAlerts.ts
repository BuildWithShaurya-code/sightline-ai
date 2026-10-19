import {useEffect,useRef,useState} from 'react';
import type {Detection} from '../types/sightline.ts';
import type {FramePrediction} from './useFrameDetection.ts';
import {MaskAlertGate, getSirenStatus, subscribeSiren, enableSiren, playMaskSiren, stopSiren} from '../services/maskAlerts.ts';

interface MaskWarning { confidence: number; time: string; }
export function useMaskAlerts(prediction: FramePrediction | null, source: string | null, enabled: boolean, completedDetections?: Detection[]) {
  const [warning,setWarning] = useState<MaskWarning|null>(null);
  const [audio,setAudio] = useState(getSirenStatus);
  const [permission,setPermission] = useState<string>(() => typeof Notification === 'undefined' ? 'unsupported' : Notification.permission);
  const [notificationError,setNotificationError] = useState('');
  const gate = useRef(new MaskAlertGate());
  const previous = useRef<FramePrediction|null>(null);
  const previousCompleted = useRef<Detection[]|undefined>(undefined);
  const desktop = useRef<Notification|null>(null);
  const closeTimer = useRef<ReturnType<typeof setTimeout>|undefined>(undefined);
  useEffect(() => subscribeSiren(setAudio),[]);
  useEffect(() => {
    gate.current = new MaskAlertGate(); previous.current = null; previousCompleted.current = undefined; setWarning(null); stopSiren();
    return () => {stopSiren(); desktop.current?.close(); clearTimeout(closeTimer.current);};
  },[source,enabled]);
  useEffect(() => {
    if (!enabled || !source) return;
    let confidence: number | null = null;
    if (completedDetections && previousCompleted.current !== completedDetections) {
      previousCompleted.current = completedDetections;
      confidence = gate.current.observeDetections(completedDetections, performance.now());
    } else {
      if (!prediction) {previous.current = null; return;}
      if (previous.current === prediction) return;
      previous.current = prediction;
      confidence = gate.current.observe(prediction,performance.now());
    }
    if (confidence === null) return;
    setWarning({confidence,time:new Date().toLocaleTimeString()});
    playMaskSiren();
    if (typeof Notification !== 'undefined' && Notification.permission === 'granted') {
      try {
        desktop.current?.close(); clearTimeout(closeTimer.current);
        desktop.current = new Notification('SightLine: threat detected', {body:`Mask prediction ${Math.round(confidence*100)}%. Review the camera or video.`,tag:'sightline-mask-alert'});
        closeTimer.current = setTimeout(() => desktop.current?.close(),10000);
      } catch {setNotificationError('Desktop notifications are unavailable here. The on-screen alert remains active.');}
    }
  },[prediction,source,enabled,completedDetections]);
  async function requestNotifications() {
    if (typeof Notification === 'undefined') {setPermission('unsupported'); return;}
    try {setPermission(await Notification.requestPermission());}
    catch {setNotificationError('The browser blocked desktop notifications. On-screen alerts still work.');}
  }
  return {warning,audio,permission,notificationError,requestNotifications,
    dismiss:() => {setWarning(null);stopSiren();desktop.current?.close();},
    silence:stopSiren,
    enable:async () => {if(await enableSiren()) {if(warning) playMaskSiren();}},
    play:async () => {if(await enableSiren()) playMaskSiren();},
  };
}

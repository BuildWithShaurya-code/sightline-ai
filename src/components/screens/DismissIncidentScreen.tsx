import {useEffect,useRef,useState} from 'react';
import {getIncident,getCachedIncident,recordSecurityResponse} from '../../services/api.ts';
import type {Incident} from '../../types/sightline.ts';
import {MaterialIcon} from '../common/MaterialIcon.tsx';
import {HoldToDismissButton} from '../common/HoldToDismissButton.tsx';

export function DismissIncidentScreen({incidentId,onBack,onDismissed}:{incidentId?:string|null;onBack:()=>void;onDismissed:()=>void}) {
  const [incident,setIncident]=useState<Incident|null>(()=>incidentId?getCachedIncident(incidentId):null),[loading,setLoading]=useState(()=>!incidentId||!getCachedIncident(incidentId)),[error,setError]=useState(''),[busy,setBusy]=useState(false);
  const [reason,setReason]=useState('');
  const reasonInput=useRef<HTMLSelectElement>(null);
  useEffect(()=>{const controller=new AbortController();const cached=incidentId?getCachedIncident(incidentId):null;setIncident(cached);setReason('');setLoading(!cached);setError('');
    if(!incidentId){setLoading(false);return;}
    getIncident(incidentId,{signal:controller.signal}).then(i=>{if(!controller.signal.aborted)setIncident(i);}).catch(e=>{if(!controller.signal.aborted)setError(e.message||'Unable to load incident');}).finally(()=>{if(!controller.signal.aborted)setLoading(false);});
    return()=>controller.abort();},[incidentId]);
  async function dismiss(){
    if(!incident||incident.status==='dismissed')return;
    if(!reason)throw new Error('Choose a false-alarm reason before dismissing.');
    await recordSecurityResponse(incident.id,'false_alarm','owner',reason);
    onDismissed();
  }
  return <div className="w-full min-h-screen bg-[#051424] text-[#d4e4fa] flex flex-col font-sans">
    <header className="flex items-center gap-3 px-5 py-5 border-b border-[#273647]/70">
      <button disabled={busy} onClick={onBack} aria-label="Back to incident" className="w-10 h-10 rounded-xl border border-[#354456] bg-[#122131] text-white flex items-center justify-center disabled:opacity-40"><MaterialIcon name="arrow_back" className="text-xl"/></button>
      <div><h1 className="text-lg font-semibold tracking-tight text-white">Dismiss incident</h1><p className="text-xs text-[#94a3b8] mt-0.5">Review before closing this alert</p></div>
    </header>
    <section aria-label="Dismissal confirmation" className="w-full max-w-lg mx-auto px-5 py-7 flex flex-col gap-5">
      {loading?<p role="status">Loading incident…</p>:error?<p role="alert" className="text-red-200">{error}</p>:!incident?<p>No incident selected.</p>:<>
        <div><h2 className="text-[28px] leading-tight font-semibold tracking-tight text-white">Is this a false alarm?</h2><p className="text-sm text-[#a7b6c8] leading-relaxed mt-2">Check the evidence before dismissing. If you’re unsure, keep the incident open.</p></div>
        <div className="flex items-center gap-3 rounded-2xl border border-[#273647] bg-[#0d1c2d] p-3">
          {incident.frames[0]?.imageDataUrl?<img src={incident.frames[0].imageDataUrl} alt="Incident evidence preview" className="w-16 h-16 rounded-xl object-cover shrink-0"/>:<div className="w-14 h-14 rounded-xl bg-[#1c2b3c] flex items-center justify-center shrink-0"><MaterialIcon name="videocam_off" className="text-2xl text-[#94a3b8]"/></div>}
          <div className="min-w-0"><p className="text-sm font-semibold text-white">{incident.id.startsWith('INC-AUTO-')?'Mask detected':incident.title||'Security alert'}</p><p className="text-xs text-[#94a3b8] mt-1">{incident.zone||'Camera incident'}</p><p className="text-[11px] text-[#94a3b8] mt-1 break-all">{incident.id}</p></div>
        </div>
        {incident.status==='dismissed'?<p className="text-[#4edea3]">This incident is already dismissed.</p>:<>
          <div className="rounded-2xl border border-[#273647] bg-[#0d1c2d] p-4"><label htmlFor="dismiss-reason" className="block text-sm font-medium text-white">False-alarm reason <span className="text-[#94a3b8] text-xs">(required)</span></label><select ref={reasonInput} id="dismiss-reason" required aria-required="true" disabled={busy} value={reason} onChange={e=>setReason(e.target.value)} aria-describedby="dismiss-reason-help" className="mt-3 w-full min-h-12 rounded-xl border border-[#354456] bg-[#051424] text-white px-3 text-sm"><option value="" disabled>Choose a reason</option><option>Other</option><option>Family member</option><option>Pet</option><option>Delivery</option><option>Model error</option></select><p id="dismiss-reason-help" className="text-xs text-[#94a3b8] mt-2">{reason?'Reason selected. Hold the button below to dismiss.':'Select a reason to enable dismissal.'}</p></div>
          <div className="rounded-3xl border border-[#354456] bg-[#0d1c2d] px-4 py-5">
            <div className="flex justify-center mb-5"><span className="inline-flex items-center gap-1.5 text-xs font-medium text-[#4edea3] rounded-full border border-[#4edea3]/20 bg-[#4edea3]/5 px-3 py-1.5"><MaterialIcon name="touch_app" className="text-base"/>3-second safety hold</span></div>
            <HoldToDismissButton key={incident.id} onConfirm={dismiss} onBusyChange={setBusy} disabled={!reason} onBlocked={()=>{reasonInput.current?.focus();reasonInput.current?.scrollIntoView({block:'center',behavior:'smooth'});}}/>
          </div>

        </>}
        <button disabled={busy} onClick={onBack} className="w-full min-h-[48px] rounded-xl border border-[#405268] bg-[#1c2b3c] text-white font-semibold text-sm disabled:opacity-40">Keep incident open</button>
        <p className="text-xs leading-relaxed text-[#94a3b8] text-center px-3">Dismissing clears the photos from this alert and returns you to the dashboard.</p>
      </>}
    </section>
  </div>;
}

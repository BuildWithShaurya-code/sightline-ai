import React, { useEffect, useRef, useState } from 'react';
import { Phone, Shield, Copy, MessageCircle, Check, Download, ArrowLeft, MapPin, Clock, FileText, ChevronRight, Circle } from 'lucide-react';
import { BottomNavigation } from '../navigation/BottomNavigation.tsx';
import { Incident, ScreenId } from '../../types/sightline.ts';
import { getIncident, getSecurityResponse, recordSecurityResponse, downloadEvidenceImage } from '../../services/api.ts';
import {useSecuritySetup} from '../../hooks/useSecuritySetup.ts';
import {setupAddress} from '../../services/securitySetup.ts';
import { defaultContacts, eventLabel, shortIncidentSummary, contactConfirmed, reportForIncident, whatsappUrl, ResponseContacts, SecurityResponse, ResponseKind, Recipient } from '../../services/securityResponse.ts';

interface Props { incidentId?: string | null; onBack?: () => void; onNavigate?: (screen: ScreenId, id?: string) => void; onFalseAlarmCleared?: () => void; }
const panel = 'rounded-2xl border border-[#273647] bg-[#0d1c2d] p-4';
const button = 'min-h-[44px] rounded-xl border border-[#273647] bg-[#1c2b3c] px-3 py-3 text-xs font-bold text-[#d4e4fa] flex items-center justify-center gap-2 hover:border-[#4edea3]/60 disabled:opacity-40 disabled:cursor-not-allowed transition-colors';
const field = 'w-full rounded-xl border border-[#273647] bg-[#051424] px-3 py-3 text-sm text-white focus:outline-none focus:border-[#4edea3]';
export const SecurityResponseScreen: React.FC<Props> = ({ incidentId, onBack, onNavigate, onFalseAlarmCleared }) => {
  const [incident, setIncident] = useState<Incident | null>(null);
  const setup=useSecuritySetup();
  const contacts:ResponseContacts=setup.details?{securityName:setup.details.contactName,securityPhone:setup.details.phone,whatsappPhone:setup.details.usePhoneForWhatsapp?setup.details.phone:setup.details.whatsappPhone,policePhone:'112',siteAddress:setupAddress(setup.details)}:defaultContacts;
  const [response, setResponse] = useState<SecurityResponse>({status: 'Not contacted', events: []});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [feedback, setFeedback] = useState('');
  const [busy, setBusy] = useState(false);
  const busyRef = useRef(false);
  const [description, setDescription] = useState('');
  const [frameIndex, setFrameIndex] = useState(0);
  const mounted = useRef(true);
  const currentId = useRef(incidentId);
  currentId.current = incidentId;
  const pendingEvent = useRef<{kind: ResponseKind; recipient: Recipient; detail: string; id: string} | null>(null);
  useEffect(() => {
    mounted.current = true;
    const controller = new AbortController();
    setIncident(null); setLoading(true); setError(''); setResponse({status:'Not contacted',events:[]});
    setDescription(''); setFrameIndex(0); pendingEvent.current = null;
    if (!incidentId) { setLoading(false); return () => { mounted.current = false; controller.abort(); }; }
    Promise.all([getIncident(incidentId, {signal: controller.signal}), getSecurityResponse(incidentId, {signal: controller.signal})])
      .then(([inc, res]) => { if (!controller.signal.aborted) { setIncident(inc); setDescription(''); setResponse(res); } })
      .catch(e => { if (!controller.signal.aborted) setError(e.message || 'Unable to load incident'); })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => { mounted.current = false; controller.abort(); };
  }, [incidentId]);
  useEffect(()=>{
    const data=setup.details;
    const next:ResponseContacts=data?{securityName:data.contactName,securityPhone:data.phone,whatsappPhone:data.usePhoneForWhatsapp?data.phone:data.whatsappPhone,policePhone:'112',siteAddress:setupAddress(data)}:defaultContacts;
    if(incident)setDescription(shortIncidentSummary(incident,next));
  },[setup.details,setup.accountRevision,incident]);
  const closed = response.status === 'Resolved' || response.status === 'False alarm' || incident?.status === 'dismissed';
  const report = incident ? reportForIncident(incident, contacts, description) : '';
  async function persist(kind: ResponseKind, recipient: Recipient = 'owner', detail = '') {
    if (!incident) throw new Error('Select an incident first');
    const prior = pendingEvent.current;
    const event = prior && prior.kind === kind && prior.recipient === recipient && prior.detail === detail ? prior : {kind,recipient,detail,id:crypto.randomUUID()};
    pendingEvent.current = event;
    const updated = await recordSecurityResponse(incident.id, kind, recipient, detail, event.id);
    if (pendingEvent.current === event) pendingEvent.current = null;
    if (mounted.current && currentId.current === incident.id) setResponse(updated);
  }
  async function run(action: () => Promise<void>) {
    if (busyRef.current) return;
    busyRef.current = true; setBusy(true); setError(''); setFeedback('');
    try { await action(); } catch(e) { if (mounted.current) setError(e instanceof Error ? e.message : 'Action failed. Please retry.'); }
    finally { busyRef.current = false; if (mounted.current) setBusy(false); }
  }
  function editContacts() { onNavigate?.('security-setup',incidentId||undefined); }
  const copy = async (value: string) => { await navigator.clipboard.writeText(value); setFeedback('Copied to clipboard'); };
  // Links launch only on an explicit user click. Opening a link does not prove a call connected or a message was sent.
  const logLaunch = (kind: ResponseKind, recipient: Recipient) => {
    void run(async () => { await persist(kind, recipient); setFeedback(kind === 'call_opened' ? 'Call link opened. Confirm below if you spoke to someone.' : 'WhatsApp opened. Review and press Send there; then confirm below.'); });
  };
  async function download() {
    const frame = incident?.frames[frameIndex]; if (!frame) return;
    const blob = await downloadEvidenceImage(frame.imageDataUrl);
    const url = URL.createObjectURL(blob); const a = document.createElement('a'); a.href = url; a.download = `${incident!.id}-evidence-${frameIndex+1}.jpg`; a.click();
    setTimeout(() => URL.revokeObjectURL(url), 10000); setFeedback('Evidence download opened');
  }
  return <div className="w-full min-h-screen flex flex-col text-[#d4e4fa] pb-24">
    <header className="px-4 py-4 border-b border-[#273647] flex items-center gap-3 bg-[#051424]">
      <button onClick={onBack} aria-label="Back to incident" className={button}><ArrowLeft size={20}/></button>
      <div className="min-w-0"><h1 className="font-mono text-sm font-bold uppercase tracking-wider text-white">Security Response</h1><p className="text-[10px] font-mono text-[#4edea3] break-all">{incidentId || 'Select an incident'}</p></div>
      <Shield size={24} className="ml-auto shrink-0 text-[#4edea3]"/>
    </header>
    <div className="flex flex-col gap-4 p-4">
      {loading && <p role="status" className={panel}>Loading incident response…</p>}
      {error && <div role="alert" className="rounded-xl border border-red-400/60 bg-red-950/40 p-3 text-sm text-red-200">{error}{!incident && <button className={button+' mt-2'} onClick={() => window.location.reload()}>Retry</button>}</div>}
      {feedback && <p role="status" className="text-sm text-[#4edea3]">{feedback}</p>}
      {!loading && !incident && !error && <div className={panel}><p>No incident selected.</p><button className={button+' mt-3'} onClick={() => onNavigate?.('history-logs')}>Open History</button></div>}
      {incident && <>
        <section className="rounded-2xl border border-[#4edea3]/50 bg-[#0d1c2d] p-4">
          <div className="flex items-center gap-2 text-[#4edea3] text-xs font-mono uppercase"><span className="w-2 h-2 rounded-full bg-current"/>{response.status}</div>
          <h2 className="mt-2 text-xl font-bold text-white">Respond to this incident</h2>
          <p className="mt-2 text-xs leading-relaxed text-[#94a3b8]">You control the response. Call and WhatsApp links open your apps. SightLine cannot verify connection, message delivery, or emergency-service attendance.</p>
        </section>
        <section className={panel+' overflow-hidden'} aria-label="Incident evidence and details">
          <div className="flex justify-between text-xs font-mono mb-3"><span>KEYFRAME EVIDENCE</span><span className="text-[#4edea3]">{incident.frames.length} {incident.frames.length === 1 ? 'PHOTO' : 'PHOTOS'}</span></div>
          {incident.frames[frameIndex] ? <img src={incident.frames[frameIndex].imageDataUrl} alt="Captured evidence for this incident" className="w-full aspect-video object-contain rounded-xl bg-[#010f1f]"/> : <div className="aspect-video flex flex-col items-center justify-center gap-2 rounded-xl bg-[#051424] text-[#94a3b8]"><FileText size={28}/><span className="text-sm">No evidence captured</span></div>}
          {incident.frames.length > 1 && <div className="flex flex-wrap gap-2 mt-2">{incident.frames.map((f,i) => <button key={f.id} aria-pressed={i===frameIndex} className={button} onClick={() => setFrameIndex(i)}>Photo {i+1}</button>)}</div>}
          <h3 className="mt-3 font-bold text-white">{incident.title || 'Security incident'}</h3>
          <p className="text-xs mt-2 flex gap-2"><Clock size={14}/>{new Date(incident.createdAt).toLocaleString()}</p>
          <p className="text-xs mt-2 flex gap-2"><MapPin size={14} className="shrink-0"/>{contacts.siteAddress || 'Exact address not added'} · {incident.zone || 'Zone not specified'}</p>
          <p className="text-xs text-[#94a3b8] mt-2 break-all">Camera: {incident.channel || incident.sourceId}</p>
          <div className="flex flex-wrap gap-2 mt-3">{incident.detections.filter((d,i,all) => i === all.findIndex(other => other.classId === d.classId && other.confidence === Math.max(...all.filter(x => x.classId === d.classId).map(x => x.confidence)))).map(d => <span key={d.classId} className="rounded-full border border-[#4edea3]/40 px-2 py-1 text-xs text-[#4edea3]">{d.classId} {Math.round(d.confidence*100)}%</span>)}</div>
          <p className="text-xs text-[#94a3b8] mt-3 leading-relaxed">Rule: {incident.reason || 'No detection rule recorded. Operator-reported incident.'}</p>
          <p className="text-xs text-[#94a3b8] mt-2">Review: {incident.status}. A model detection is not proof of theft.</p>
        </section>
        {incident.status!=='confirmed' ? <section role="alert" className={panel+' text-amber-200'}><p className="font-bold">Threat not confirmed</p><p className="text-xs mt-2">Confirm the threat before contacting police or security.</p><button className={button+' mt-3'} onClick={()=>onNavigate?.('threat-detail',incident.id)}>Review and confirm threat</button></section> : <>
        {setup.error&&<p className="text-xs text-amber-100 leading-relaxed rounded-xl border border-amber-400/25 bg-amber-400/5 p-3">{setup.error}</p>}
        <section aria-label="Contact actions" className="flex flex-col gap-3">
          <div className="flex items-center justify-between"><h2 className="font-mono text-xs uppercase tracking-wider">Contact help</h2><button className="text-xs text-[#4edea3] min-h-[44px] underline" onClick={editContacts}>Edit contacts & address</button></div>
          <div className="grid grid-cols-2 gap-3">
            {contacts.securityPhone ? <a aria-disabled={busy || closed} href={closed || busy ? undefined : `tel:${contacts.securityPhone}`} onClick={() => {if(!closed&&!busy) logLaunch('call_opened','security');}} className={button+' !bg-[#12352f] !border-[#4edea3]/50 !text-[#4edea3] flex-col'}><Phone size={22}/><span>Call Security</span><span className="font-normal text-[11px]">{contacts.securityName || contacts.securityPhone}</span></a> : <button disabled={closed||setup.loading} onClick={editContacts} className={button+' flex-col !text-[#4edea3]'}><Phone size={22}/><span>Call Security</span><span className="text-[11px] font-normal">Add security contact</span></button>}
            <a aria-disabled={busy || closed} href={closed || busy ? undefined : `tel:${contacts.policePhone}`} onClick={() => {if(!closed&&!busy) logLaunch('call_opened','police');}} className={button+' flex-col !bg-[#b91c28] !border-[#ff5451]/60 !text-white'}><Shield size={22}/><span>Call Police</span><span className="text-[11px] font-normal">{contacts.policePhone}</span></a>
          </div>
          <div className="grid grid-cols-2 gap-3"><button disabled={!contacts.securityPhone || setup.loading} className={button} onClick={() => void run(() => copy(contacts.securityPhone))}><Copy size={14}/>Copy security number</button><button className={button} onClick={() => void run(() => copy(contacts.policePhone))}><Copy size={14}/>Copy police number</button></div>
          <p className="text-[11px] text-[#94a3b8]">112 is India’s unified emergency number. On a laptop, copy the number and call from your phone.</p>
        </section>
        <section className={panel+' flex flex-col gap-3'} aria-label="Share incident summary">
          <h2 className="font-mono text-xs uppercase">Share summary</h2>
          <label className="text-xs text-[#94a3b8]">Incident summary (automatically generated; editable)<textarea className={field+' mt-2'} maxLength={1000} value={description} onChange={e => setDescription(e.target.value)} placeholder="Describe what you can see; verify your exact location."/></label>
          <details><summary className="text-xs text-[#4edea3] cursor-pointer py-2">Preview report</summary><pre className="text-xs whitespace-pre-wrap leading-relaxed mt-2 text-[#94a3b8]">{report}</pre></details>
          <button disabled={busy} className={button} onClick={() => void run(async () => {await copy(report); if(!closed) await persist('summary_copied','police');})}><Copy size={16}/>Copy report for police</button>
          {contacts.securityPhone ? <a className={button+' !text-[#4edea3]'} href={closed || busy ? undefined : whatsappUrl(contacts.whatsappPhone || contacts.securityPhone,report)} target="_blank" rel="noopener noreferrer" onClick={() => {if(!closed&&!busy) logLaunch('whatsapp_opened','security');}}><MessageCircle size={16}/>Share with security on WhatsApp<ChevronRight size={14}/></a> : <button disabled={closed} className={button} onClick={editContacts}><MessageCircle size={16}/>Add security contact to share</button>}
          <p className="text-[11px] leading-relaxed text-[#94a3b8]">WhatsApp opens a draft summary. Press Send there. Evidence photos are downloaded separately; they are not attached automatically.</p>
          <button disabled={busy || closed || !contacts.securityPhone || setup.loading} className={button} onClick={() => void run(() => persist('summary_shared','security'))}>I sent the summary to security</button>
        </section>
        <section className={panel} aria-label="Response timeline">
          <h2 className="font-mono text-xs uppercase mb-4">Response timeline</h2>
          <ol className="border-l border-[#273647] ml-1 pl-4 flex flex-col gap-4 text-xs">
            <li><p className="text-[#94a3b8]">Incident recorded · Not contacted</p><time className="text-[10px] text-[#94a3b8]">{new Date(incident.createdAt).toLocaleString()}</time></li>
            {response.events.map(e => <li key={e.id}><p className="font-semibold text-[#4edea3]">{eventLabel(e)}</p>{e.detail && <p className="mt-1 break-words text-[#d4e4fa]">{e.detail}</p>}<time className="text-[10px] text-[#94a3b8]">{new Date(e.createdAt).toLocaleString()}</time></li>)}
          </ol>
          <div className="flex flex-col gap-2 mt-4">{(['security','police'] as const).map(who=>{
            const confirmed=contactConfirmed(response,who);
            return <button key={who} role="checkbox" aria-checked={confirmed} disabled={busy || closed || confirmed} className={button+(confirmed?' !text-[#4edea3] !border-[#4edea3]/50':'')} onClick={() => void run(() => persist('contact_confirmed',who))}>{confirmed?<Check size={14}/>:<Circle size={14}/>}<span>{confirmed?`${who==='police'?'Police':'Security'} conversation confirmed by you`:`I spoke to ${who}`}</span></button>;
          })}</div>
          <p className="text-[11px] text-[#94a3b8] mt-2">These confirmations are reported by you, not by police or security.</p>
        </section>
        <section className={panel+' flex flex-col gap-3'} aria-label="Response follow-up">
          <h2 className="font-mono text-xs uppercase">Response follow-up</h2>
          <p className="text-sm text-[#4edea3]">{incident.status==='confirmed'?'Threat confirmed by you. Evidence is preserved for follow-up.':'Review and confirm this incident before closing the response.'}</p>
          <button className={button} onClick={() => onNavigate?.('threat-detail',incident.id)}><Shield size={16}/>View incident confirmation & evidence<ChevronRight size={14}/></button>
          <button disabled={busy || !incident.frames.length} className={button} onClick={() => void run(download)}><Download size={16}/>Download evidence photo</button>
          <button disabled={busy || closed || incident.status!=='confirmed'} className={button+' !border-[#4edea3]/50 !text-[#4edea3]'} onClick={() => void run(() => persist('resolved'))}>{response.status==='Resolved'?<Check size={16}/>:<Circle size={16}/>} {response.status==='Resolved'?'Response completed · confirmed by you':'Mark response completed'}</button>
          <button className={button} onClick={() => onNavigate?.('dashboard')}>Return to dashboard</button>
        </section>
        </>}
      </>}
    </div>
    <BottomNavigation activeScreen="security-response" onNavigate={onNavigate}/>
  </div>;
};

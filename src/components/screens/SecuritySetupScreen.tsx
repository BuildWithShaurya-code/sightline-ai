import {useEffect,useRef,useState} from 'react';
import {SecurityPinSettings} from '../common/SecurityPinSettings.tsx';
import {MaterialIcon} from '../common/MaterialIcon.tsx';
import {BottomNavigation} from '../navigation/BottomNavigation.tsx';
import {emptySecuritySetup,validateSecuritySetup,type SecuritySetup,type SetupErrors} from '../../services/securitySetup.ts';
import {securitySetupStore,useSecuritySetup} from '../../hooks/useSecuritySetup.ts';
import {createSetupAutosave,type AutosaveState} from '../../services/setupAutosave.ts';
import type {ScreenId} from '../../types/sightline.ts';

const inputClass='account-input w-full min-h-[48px] scroll-mb-28 rounded-xl border bg-[#051424] px-3 py-3 text-sm text-white placeholder:text-[#72849b] outline-none focus:border-[#4edea3]';
export function SecuritySetupScreen({onDone,onSaved,onNavigate}:{onDone:()=>void;onSaved:()=>void;onNavigate?:(screen:ScreenId)=>void}) {
  const {details,loading,error:loadError,accountRevision,ownerId}=useSecuritySetup();
  const [draft,setDraft]=useState<SecuritySetup>({...emptySecuritySetup}),[errors,setErrors]=useState<SetupErrors>({}),[saving,setSaving]=useState(false),[error,setError]=useState('');
  const [saveState,setSaveState]=useState<AutosaveState>({status:'idle'});
  const busy=useRef(false),mounted=useRef(true),account=useRef(accountRevision),dirty=useRef(false);
  const autosave=useRef<ReturnType<typeof createSetupAutosave<SecuritySetup>>|null>(null);
  account.current=accountRevision;
  useEffect(()=>{mounted.current=true;return()=>{mounted.current=false;};},[]);
  useEffect(()=>{dirty.current=false;setDraft({...emptySecuritySetup});setErrors({});setError('');setSaveState({status:'idle'});},[accountRevision]);
  useEffect(()=>{if(details&&!dirty.current)setDraft(details);},[details]);
  useEffect(()=>{
    if(!ownerId||loading||loadError)return;
    const controller=createSetupAutosave<SecuritySetup>(value=>securitySetupStore.save(value,ownerId),setSaveState);
    if(details)controller.prime(details);
    autosave.current=controller;
    return()=>{controller.dispose();if(autosave.current===controller)autosave.current=null;};
  },[ownerId,accountRevision,loading,loadError,details]);
  useEffect(()=>{
    if(!dirty.current||loading)return;
    const check=validateSecuritySetup(draft);
    if(Object.keys(check.errors).length){autosave.current?.invalidate();return;}
    autosave.current?.schedule(check.data);
  },[draft,loading,ownerId,accountRevision,loadError]);
  const formRef=useRef<HTMLFormElement>(null);
  function update<K extends keyof SecuritySetup>(key:K,value:SecuritySetup[K]){dirty.current=true;setDraft(d=>({...d,[key]:value}));setErrors(e=>({...e,[key]:undefined}));setError('');}
  async function submit(e:React.FormEvent){
    e.preventDefault();if(busy.current)return;
    const check=validateSecuritySetup(draft);setErrors(check.errors);
    if(Object.keys(check.errors).length){requestAnimationFrame(()=>formRef.current?.querySelector<HTMLInputElement>('[aria-invalid="true"]')?.focus());return;}
    busy.current=true;setSaving(true);setError('');const startedAccount=account.current;
    try{
      const controller=autosave.current;
      if(!controller)throw new Error(loadError||'Your session has ended. Sign in again to save your details securely.');
      const saved=await controller.flush(check.data);
      if(saved&&mounted.current&&startedAccount===account.current)onSaved();
    } catch(e){if(mounted.current&&startedAccount===account.current)setError(e instanceof Error?e.message:'Details were not saved. Please retry.');}
    finally{busy.current=false;if(mounted.current)setSaving(false);}
  }
  function field(key:Exclude<keyof SecuritySetup,'usePhoneForWhatsapp'>,label:string,placeholder:string,required=true,phone=false){
    const message=errors[key];return <div key={key}><label htmlFor={`setup-${key}`} className="block text-xs font-medium text-[#d4e4fa] mb-2">{label}{!required&&<span className="text-[#94a3b8]"> (optional)</span>}</label><div className="relative">{phone&&<span className="absolute left-3 top-3.5 text-sm text-[#94a3b8] pointer-events-none">+91</span>}<input id={`setup-${key}`} name={key} value={phone?draft[key].replace(/^\+91/,''):draft[key]} onChange={e=>update(key,e.target.value)} required={required} type={phone?'tel':'text'} inputMode={phone?'tel':key==='pinCode'?'numeric':'text'} autoComplete={key==='fullAddress'?'street-address':key==='city'?'address-level2':key==='state'?'address-level1':key==='pinCode'?'postal-code':'off'} maxLength={key==='fullAddress'?500:key==='landmark'?200:phone?18:key==='pinCode'?6:100} placeholder={placeholder} aria-invalid={!!message} aria-describedby={message?`setup-${key}-error`:undefined} disabled={loading||saving} className={inputClass+(message?' border-red-400':' border-[#273647]')+(phone?' pl-12':'')}/></div>{message&&<p id={`setup-${key}-error`} className="mt-1.5 text-xs text-red-200">{message}</p>}</div>;
  }
  return <div className="min-h-screen w-full text-[#d4e4fa] pb-[calc(6rem+env(safe-area-inset-bottom))]">
    <header className="flex items-center gap-3 px-4 py-5 border-b border-[#273647]"><button type="button" disabled={saving} aria-label="Back from security setup" onClick={onDone} className="w-10 h-10 rounded-xl border border-[#273647] bg-[#1c2b3c] flex items-center justify-center"><MaterialIcon name="arrow_back"/></button><div className="min-w-0"><h1 className="font-semibold text-lg text-white tracking-tight leading-tight">Security contacts &amp; location</h1><p className="text-xs text-[#94a3b8] mt-1">Be ready when an incident needs your attention.</p></div></header>
    <form ref={formRef} onSubmit={submit} noValidate className="flex flex-col gap-5 p-4">
      {loading&&<p role="status" className="text-xs text-[#94a3b8]">Loading your private account details…</p>}
      {loadError&&<div role="status" className="rounded-xl border border-amber-400/30 bg-amber-400/5 p-3 text-xs text-amber-100 leading-relaxed">{loadError}</div>}
      <fieldset disabled={saving} className="rounded-2xl border border-[#273647] bg-[#0d1c2d] p-4 flex flex-col gap-4"><legend className="sr-only">Property location</legend><h2 className="flex items-center gap-2 text-sm font-semibold text-white"><MaterialIcon name="location_on" className="text-[#4edea3] text-xl"/>Property location</h2>
        {field('propertyName','Property name','e.g. Lakeview Residence')}{field('fullAddress','Full address','House / flat, building, street and area')}
        <div className="grid grid-cols-1 min-[360px]:grid-cols-2 gap-4">{field('city','City','e.g. Jaipur')}{field('state','State','e.g. Rajasthan')}</div>
        {field('pinCode','PIN code','Six-digit PIN code')}{field('landmark','Nearby landmark','e.g. Opposite the community park',false)}
      </fieldset>
      <fieldset disabled={saving} className="rounded-2xl border border-[#273647] bg-[#0d1c2d] p-4 flex flex-col gap-4"><legend className="sr-only">Security contact</legend><h2 className="flex items-center gap-2 text-sm font-semibold text-white"><MaterialIcon name="shield" className="text-[#4edea3] text-xl"/>Security contact</h2>
        {field('contactName','Contact name','Enter contact name')}{field('phone','Phone number','10-digit phone number',true,true)}
        <label className="flex items-center gap-3 min-h-[44px] text-sm cursor-pointer"><input type="checkbox" checked={draft.usePhoneForWhatsapp} onChange={e=>update('usePhoneForWhatsapp',e.target.checked)} disabled={loading||saving} className="w-4 h-4 accent-[#4edea3]"/>Use this number for WhatsApp</label>
        {!draft.usePhoneForWhatsapp&&field('whatsappPhone','WhatsApp number','10-digit WhatsApp number',true,true)}
      </fieldset>
      <p role="status" aria-live="polite" className="flex items-center gap-2 text-xs text-[#94a3b8] min-h-5"><MaterialIcon name={saveState.status==='saved'?'check_circle':saveState.status==='saving'?'sync':'lock'} className={saveState.status==='saving'?'text-base animate-spin':'text-base text-[#4edea3]'}/>{saveState.status==='saved'?'All changes saved to your account':saveState.status==='saving'?'Saving changes…':saveState.status==='waiting'?'Changes waiting to save…':'Complete the required fields to save automatically.'}</p>
      {(error||saveState.error)&&<p role="alert" className="rounded-xl border border-red-400/40 bg-red-950/30 p-3 text-sm text-red-200">{error||saveState.error}</p>}
      <button type="submit" disabled={loading||saving} className="w-full scroll-mb-28 min-h-[50px] rounded-full bg-[#4edea3] text-[#003824] flex items-center justify-center gap-2 font-semibold text-sm hover:brightness-105 disabled:opacity-50"><MaterialIcon name={saving?'sync':'check'} className={saving?'animate-spin text-lg':'text-lg'}/>{saving?'Saving details…':'Save details'}</button>
      <p className="text-xs leading-relaxed text-[#94a3b8] text-center px-2">Private to your signed-in account. Saving does not make a call or send a message. You review and send WhatsApp messages yourself.</p>
    </form>
    {ownerId&&<details className="mx-4 mb-5 rounded-2xl border border-[#273647] bg-[#0d1c2d]"><summary className="px-4 py-3 text-xs text-[#94a3b8] cursor-pointer">Advanced: dispatch security PIN</summary><SecurityPinSettings owner={ownerId}/></details>}
    <BottomNavigation activeScreen="security-setup" onNavigate={onNavigate}/>
  </div>;
}

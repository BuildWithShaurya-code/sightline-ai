import {useEffect,useRef,useState} from 'react';
import {loadSecurityPinStatus,saveSecurityPin} from '../../services/auth.ts';

export function SecurityPinSettings({owner}:{owner:string}){
  const [configured,setConfigured]=useState<boolean|null>(null),[current,setCurrent]=useState(''),[pin,setPin]=useState(''),[confirm,setConfirm]=useState('');
  const [error,setError]=useState(''),[message,setMessage]=useState(''),[saving,setSaving]=useState(false);
  const revision=useRef(0),busy=useRef(false);
  useEffect(()=>{
    const version=++revision.current;setConfigured(null);setCurrent('');setPin('');setConfirm('');setError('');setMessage('');
    if(owner)void loadSecurityPinStatus(owner).then(value=>{if(version===revision.current)setConfigured(value);}).catch(e=>{if(version===revision.current)setError(e.message||'Could not load security PIN settings.');});
    return()=>{++revision.current;};
  },[owner]);
  async function save(){
    if(busy.current||!owner||configured===null)return;
    setError('');setMessage('');
    if(configured&&!/^[0-9]{4,8}$/.test(current)){setError('Enter your current security PIN.');return;}
    if(!/^[0-9]{4,8}$/.test(pin)){setError('Choose a security PIN containing 4–8 digits.');return;}
    if(pin!==confirm){setError('The new PINs do not match.');return;}
    busy.current=true;setSaving(true);const version=revision.current;
    try{await saveSecurityPin(owner,pin,configured?current:undefined);if(version===revision.current){setConfigured(true);setCurrent('');setPin('');setConfirm('');setMessage('Security PIN saved.');}}
    catch(e){if(version===revision.current)setError(e instanceof Error?e.message:'Your security PIN was not saved.');}
    finally{busy.current=false;if(version===revision.current)setSaving(false);}
  }
  const field='account-input w-full min-h-12 rounded-xl border border-[#354456] bg-[#051424] px-3 py-3 text-sm text-white placeholder:text-[#72849b] mt-2';
  return <form noValidate autoComplete="off" onSubmit={e=>{e.preventDefault();void save();}} className="rounded-2xl border border-[#273647] bg-[#0d1c2d] p-4">
    <h2 className="text-base font-semibold text-white">Security PIN</h2>
    <p className="text-xs text-[#94a3b8] mt-1 mb-4">{configured?'Enter your current PIN to choose a replacement.':'Choose your own PIN before using dispatch cancellation. There is no default PIN.'}</p>
    {error&&<p role="alert" className="text-sm text-red-200 mb-3">{error}</p>}
    {message&&<p role="status" className="text-sm text-[#4edea3] mb-3">{message}</p>}
    {configured===null&&!error&&<p role="status" className="text-xs text-[#94a3b8] mb-3">Checking your security PIN…</p>}
    <fieldset disabled={!owner||configured===null||saving} className="space-y-4">
      {configured&&<div><label htmlFor="security-current-pin" className="text-xs font-medium">Current security PIN</label><input id="security-current-pin" type="password" inputMode="numeric" autoComplete="off" maxLength={8} value={current} onChange={e=>setCurrent(e.target.value)} className={field}/></div>}
      <div><label htmlFor="security-new-pin" className="text-xs font-medium">New security PIN</label><input id="security-new-pin" type="password" inputMode="numeric" autoComplete="new-password" maxLength={8} value={pin} onChange={e=>setPin(e.target.value)} placeholder="Choose 4–8 digits" className={field}/></div>
      <div><label htmlFor="security-confirm-pin" className="text-xs font-medium">Confirm security PIN</label><input id="security-confirm-pin" type="password" inputMode="numeric" autoComplete="new-password" maxLength={8} value={confirm} onChange={e=>setConfirm(e.target.value)} placeholder="Enter your new PIN again" className={field}/></div>
      <button className="w-full min-h-11 rounded-full bg-[#4edea3] text-[#003824] text-sm font-semibold mt-4 disabled:opacity-50">{saving?'Saving PIN…':configured?'Change security PIN':'Set security PIN'}</button>
    </fieldset>
  </form>;
}

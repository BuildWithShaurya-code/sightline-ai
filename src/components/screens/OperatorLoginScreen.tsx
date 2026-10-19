import React,{useEffect,useRef,useState} from 'react';
import {MaterialIcon} from '../common/MaterialIcon.tsx';
import {SignInSlider} from '../common/SignInSlider.tsx';
import {login,register,validateRegistration,supabase,type RegistrationErrors} from '../../services/auth.ts';

export const OperatorLoginScreen:React.FC<{onSuccess?:()=>void;initialMode?:'signin'|'signup'}>=({onSuccess,initialMode='signin'})=>{
  const [mode,setMode]=useState<'signin'|'signup'>(initialMode);
  const [operatorId,setOperatorId]=useState(''),[password,setPassword]=useState(''),[confirm,setConfirm]=useState('');
  const [operatorEditable,setOperatorEditable]=useState(false),[passwordEditable,setPasswordEditable]=useState(false);
  const [showPassword,setShowPassword]=useState(false),[remember,setRemember]=useState(true);
  const [errors,setErrors]=useState<RegistrationErrors&{identity?:string}>({}),[error,setError]=useState(''),[notice,setNotice]=useState('');
  const [pending,setPending]=useState(false),[unlocked,setUnlocked]=useState(false),[help,setHelp]=useState(false);
  const busy=useRef(false),form=useRef<HTMLFormElement>(null),helpTrigger=useRef<HTMLButtonElement>(null),helpClose=useRef<HTMLButtonElement>(null),successTimer=useRef<ReturnType<typeof setTimeout>|undefined>(undefined);
  const creating=mode==='signup';
  useEffect(()=>()=>clearTimeout(successTimer.current),[]);
  useEffect(()=>{if(!help)return;helpClose.current?.focus();const close=(e:KeyboardEvent)=>{if(e.key==='Escape'){setHelp(false);helpTrigger.current?.focus();}};window.addEventListener('keydown',close);return()=>window.removeEventListener('keydown',close);},[help]);
  function switchMode(nextMode:'signin'|'signup'=creating?'signin':'signup'){if(busy.current||unlocked||nextMode===mode)return;setMode(nextMode);setPassword('');setConfirm('');setErrors({});setError('');setNotice('');}
  async function attempt():Promise<boolean>{
    if(busy.current||unlocked)return false;
    const input={username:operatorId,password,confirmPassword:confirm};
    const next=creating?validateRegistration(input):{identity:operatorId.trim()?undefined:'Enter your username.',password:password.trim()?undefined:'Enter your password.'};
    setErrors(next);setError('');setNotice('');
    if(Object.values(next).some(Boolean)){requestAnimationFrame(()=>form.current?.querySelector<HTMLInputElement>('[aria-invalid="true"]')?.focus());return false;}
    busy.current=true;setPending(true);
    try{
      const result=creating?await register(input,remember):await login(operatorId,password,remember);
      if(!result.success){setError(result.error||'Could not continue. Please try again.');return false;}
      setUnlocked(true);successTimer.current=setTimeout(()=>onSuccess?.(),250);return true;
    }catch{setError('Could not continue. Check your connection and try again.');return false;}
    finally{busy.current=false;setPending(false);}
  }
  const inputClass='login-input w-full min-w-0 py-3.5 bg-[#051424] border-none outline-none text-sm text-white placeholder:text-[#72849b]';
  const fieldClass=(invalid:boolean)=>`login-field flex items-center gap-3 px-3 rounded-xl border bg-[#051424] focus-within:border-[#4edea3]/70 ${invalid?'border-red-400':'border-[#273647]'}`;
  const identityError=creating?errors.username:errors.identity;
  return <div className="flex flex-col w-full min-h-screen bg-[#051424] text-[#d4e4fa] px-4 pt-9 pb-8 sm:pt-12">
    <div className="flex items-center justify-center gap-3 mb-7">
      <div className="w-11 h-11 rounded-xl border border-[#4edea3]/25 bg-[#4edea3]/5 flex items-center justify-center"><MaterialIcon name="shield" className="text-[#4edea3] text-2xl"/></div>
      <h1 className="font-sans text-3xl font-bold tracking-tight text-white">SightLine <span className="text-[#4edea3]">AI</span></h1>
    </div>
    <section aria-label="Detection capabilities" className="rounded-2xl border border-[#273647] bg-[#0d1c2d] p-4 mb-5">
      <div className="flex items-center gap-2 mb-3"><MaterialIcon name="sensors" className="text-[#4edea3] text-lg"/><h2 className="text-xs font-medium text-[#aebed0]">Three-class detection</h2></div>
      <div className="grid grid-cols-3 gap-2">{[{name:'Person',icon:'person',color:'text-[#4edea3]'},{name:'Mask',icon:'masks',color:'text-[#ffb95f]'},{name:'Knife',icon:'hardware',color:'text-[#ffb95f]'}].map(item=><div key={item.name} className="flex flex-col items-center gap-2 rounded-xl bg-[#051424] border border-[#273647]/70 py-3"><MaterialIcon name={item.icon} className={`text-xl ${item.color}`}/><span className="text-xs font-medium">{item.name}</span></div>)}</div>
    </section>
    <form ref={form} noValidate autoComplete="off" onSubmit={e=>{e.preventDefault();void attempt();}} aria-busy={pending} className="w-full rounded-3xl bg-[#0d1c2d] border border-[#273647] p-5 flex flex-col gap-5 shadow-[0_12px_36px_#0002]">
      <div className="grid grid-cols-2 gap-1 rounded-xl border border-[#273647] bg-[#051424] p-1" role="group" aria-label="Account access">{(['signin','signup'] as const).map(value=><button key={value} type="button" aria-pressed={mode===value} disabled={pending||unlocked} onClick={()=>switchMode(value)} className={`min-h-11 rounded-lg text-sm font-semibold transition-colors ${mode===value?'bg-[#1c2b3c] text-white shadow-sm':'text-[#94a3b8] hover:text-white'}`}>{value==='signin'?'Sign in':'Create account'}</button>)}</div>
      <div><h2 className="font-sans text-xl font-semibold text-white tracking-tight">{creating?'Create your account':'Welcome back'}</h2><p className="text-xs text-[#94a3b8] mt-1.5">{creating?'Choose a unique username and password. No email required.':'Have an account? Sign in below. New users can create an account above.'}</p></div>
      {error&&<p role="alert" className="rounded-xl border border-red-400/30 bg-red-950/25 text-red-200 p-3 text-xs leading-relaxed">{error}</p>}
      {notice&&<p role="status" className="rounded-xl border border-[#4edea3]/30 bg-[#4edea3]/5 text-[#a4efd2] p-3 text-xs leading-relaxed">{notice}</p>}
      <div><label htmlFor="operator-id-input" className="block text-xs font-medium mb-2">Username</label><div className={fieldClass(!!identityError)}><MaterialIcon name="person" className="text-lg text-[#94a3b8]"/><input id="operator-id-input" name="operatorIdentifier" type="text" autoComplete="off" readOnly={!operatorEditable} onFocus={()=>setOperatorEditable(true)} autoCapitalize="none" spellCheck={false} value={operatorId} maxLength={creating?32:254} disabled={pending||unlocked} onChange={e=>{setOperatorId(e.target.value);setErrors(p=>({...p,identity:undefined,username:undefined}));setError('');}} placeholder={creating?'Choose your username':'Enter your username'} aria-invalid={!!identityError} aria-describedby={identityError?'identity-error':'identity-hint'} className={inputClass}/></div>{identityError?<p id="identity-error" role="alert" className="mt-1.5 text-xs text-red-200">{identityError}</p>:<p id="identity-hint" className="text-[11px] mt-2 text-[#94a3b8]">{creating?'3–32 characters. Names with spaces and numbers are welcome.':'Use the unique username you created.'}</p>}</div>

      <div><div className="flex items-center justify-between mb-1"><label htmlFor="passcode-input" className="text-xs font-medium">Password</label>{!creating&&<button ref={helpTrigger} type="button" onClick={()=>setHelp(true)} className="text-xs text-[#4edea3] min-h-9">Sign-in help</button>}</div><div className={fieldClass(!!errors.password)}><MaterialIcon name="lock" className="text-lg text-[#94a3b8]"/><input id="passcode-input" name="operatorPasscode" type={showPassword?'text':'password'} autoComplete={creating?'new-password':'off'} readOnly={!passwordEditable} onFocus={()=>setPasswordEditable(true)} value={password} maxLength={4096} disabled={pending||unlocked} onChange={e=>{setPassword(e.target.value);setErrors(p=>({...p,password:undefined}));setError('');}} placeholder={creating?'Choose a password (8+ characters)':'Enter your password'} aria-invalid={!!errors.password} aria-describedby={errors.password?'password-error':undefined} className={inputClass}/><button type="button" aria-label={showPassword?'Hide password':'Show password'} onClick={()=>setShowPassword(!showPassword)} className="shrink-0 w-9 h-10 flex items-center justify-center text-[#94a3b8]"><MaterialIcon name={showPassword?'visibility_off':'visibility'} className="text-xl"/></button></div>{errors.password&&<p id="password-error" role="alert" className="mt-1.5 text-xs text-red-200">{errors.password}</p>}</div>
      {creating&&<div><label htmlFor="signup-confirm" className="block text-xs font-medium mb-2">Confirm password</label><div className={fieldClass(!!errors.confirmPassword)}><MaterialIcon name="lock" className="text-lg text-[#94a3b8]"/><input id="signup-confirm" type={showPassword?'text':'password'} autoComplete="new-password" value={confirm} maxLength={4096} disabled={pending||unlocked} onChange={e=>{setConfirm(e.target.value);setErrors(p=>({...p,confirmPassword:undefined}));}} placeholder="Enter your password again" aria-invalid={!!errors.confirmPassword} aria-describedby={errors.confirmPassword?'confirm-error':undefined} className={inputClass}/></div>{errors.confirmPassword&&<p id="confirm-error" role="alert" className="mt-1.5 text-xs text-red-200">{errors.confirmPassword}</p>}</div>}
      <label className="flex items-center gap-2.5 min-h-8 text-xs text-[#aebed0]"><input type="checkbox" checked={remember} disabled={pending} onChange={e=>setRemember(e.target.checked)} className="w-4 h-4 accent-[#4edea3]"/>Remember me on this device</label>
      <div className="space-y-3">{!creating&&<SignInSlider pending={pending} unlocked={unlocked} onComplete={attempt}/>}<button type="submit" disabled={pending||unlocked} className={`w-full min-h-11 rounded-full border text-sm font-semibold disabled:opacity-60 ${creating?'bg-[#4edea3] text-[#003824] border-[#4edea3]':'bg-[#1c2b3c] border-[#273647] text-white hover:bg-[#273647]'}`}>{pending?creating?'Creating account…':'Signing in…':unlocked?'Opening your security setup…':creating?'Create account':'Sign in'}</button>{!creating&&<p className="text-[11px] text-[#94a3b8] text-center">Slide the arrow, or use the sign-in button.</p>}</div>
      <p className="text-xs text-[#94a3b8] text-center">{creating?'Already have an account?':'New to SightLine?'} <button type="button" disabled={pending||unlocked} onClick={()=>switchMode()} className="text-[#4edea3] font-medium min-h-9 px-1">{creating?'Sign in':'Create an account'}</button></p>
    </form>
    <p className="flex items-center justify-center gap-1.5 text-[11px] text-[#72849b] mt-5"><MaterialIcon name="lock" className="text-sm"/>Your security details stay private to your account.</p>
    {help&&<div role="dialog" aria-modal="true" aria-labelledby="password-help-title" className="fixed inset-0 z-50 bg-[#010f1f]/80 flex items-center justify-center p-6"><div className="rounded-2xl border border-[#273647] bg-[#0d1c2d] p-5 max-w-sm"><h3 id="password-help-title" className="text-white font-semibold">Need help signing in?</h3><p className="text-sm text-[#94a3b8] leading-relaxed my-3">Sign in with your own unique username and password. New here? Close this message and choose Create an account. Accounts do not require email. If you forget your password, contact the site owner for account recovery.</p><button ref={helpClose} type="button" onClick={()=>{setHelp(false);helpTrigger.current?.focus();}} className="w-full min-h-11 rounded-full bg-[#1c2b3c] text-sm font-semibold">Got it</button></div></div>}
  </div>;
};

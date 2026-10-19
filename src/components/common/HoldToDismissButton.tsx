import {useEffect,useRef,useState} from 'react';
import {ContinuousHold} from '../../services/continuousHold.ts';
import {MaterialIcon} from './MaterialIcon.tsx';

export function HoldToDismissButton({onConfirm,onBusyChange,disabled=false,onBlocked}:{onConfirm:()=>Promise<void>;onBusyChange?:(busy:boolean)=>void;disabled?:boolean;onBlocked?:()=>void}) {
  const gate=useRef(new ContinuousHold(3000));
  const interval=useRef<ReturnType<typeof setInterval>|undefined>(undefined);
  const pressed=useRef(false),submitting=useRef(false),mounted=useRef(true);
  const [progress,setProgress]=useState(0),[busy,setBusy]=useState(false),[error,setError]=useState('');
  function clearTimer(){clearInterval(interval.current);interval.current=undefined;}
  function cancel(){pressed.current=false;gate.current.cancel();clearTimer();if(!submitting.current)setProgress(0);}
  async function commit(){
    if(submitting.current)return;
    submitting.current=true;pressed.current=false;clearTimer();setBusy(true);onBusyChange?.(true);
    try {await onConfirm();}
    catch(e){if(mounted.current)setError(e instanceof Error?e.message:'Dismissal could not be saved. Hold again to retry.');}
    finally {submitting.current=false;if(mounted.current){setBusy(false);setProgress(0);onBusyChange?.(false);}}
  }
  function tick(){
    if(!pressed.current||submitting.current)return;
    const next=gate.current.advance(performance.now());setProgress(next.progress);
    if(next.complete)void commit();
  }
  function begin(){
    if(disabled){setError('Choose a false-alarm reason above, then hold to dismiss.');onBlocked?.();return;}
    if(submitting.current||pressed.current)return;
    pressed.current=true;setError('');setProgress(0);gate.current.start(performance.now());
    interval.current=setInterval(tick,40);
  }
  function release(){tick();if(!submitting.current)cancel();}
  useEffect(()=>{
    mounted.current=true;
    const blur=()=>cancel();const visibility=()=>{if(document.hidden)cancel();};
    window.addEventListener('blur',blur);document.addEventListener('visibilitychange',visibility);
    return()=>{mounted.current=false;pressed.current=false;gate.current.cancel();clearTimer();window.removeEventListener('blur',blur);document.removeEventListener('visibilitychange',visibility);};
  },[]);
  useEffect(()=>{if(disabled)cancel();else setError('');},[disabled]);
  return <div className="flex flex-col items-center gap-3">
    <div className="rounded-full p-1.5" style={{background:`conic-gradient(#4edea3 ${progress*360}deg, #273647 0deg)`}}>
      <button type="button" disabled={busy} aria-disabled={disabled||busy} aria-describedby="dismiss-hold-help" aria-label="Hold for 3 seconds to dismiss incident"
        onPointerDown={e=>{if(e.pointerType==='mouse'&&e.button!==0)return;e.preventDefault();e.currentTarget.setPointerCapture(e.pointerId);begin();}}
        onPointerUp={release} onPointerCancel={cancel} onLostPointerCapture={()=>{if(!submitting.current)cancel();}}
        onPointerMove={e=>{if(!pressed.current)return;const r=e.currentTarget.getBoundingClientRect();if(e.clientX<r.left||e.clientX>r.right||e.clientY<r.top||e.clientY>r.bottom)cancel();}}
        onKeyDown={e=>{if(e.key===' '||e.key==='Enter'){e.preventDefault();if(!e.repeat)begin();}}}
        onKeyUp={e=>{if(e.key===' '||e.key==='Enter'){e.preventDefault();release();}}} onBlur={cancel}
        className={`w-40 h-40 rounded-full bg-gradient-to-br from-[#4edea3] to-[#16b889] border border-[#8af0c6]/60 text-[#003824] flex flex-col items-center justify-center gap-2 font-bold select-none touch-none disabled:opacity-50 focus-visible:outline-4 focus-visible:outline-[#4edea3] ${disabled?'opacity-60':''}`}>
        <MaterialIcon name={busy?'sync':'close'} className="text-[30px]"/>
        <span className="text-lg font-semibold">{busy?'Saving…':'Dismiss alert'}</span>
        <span className="text-xs font-medium text-[#003824]/80">{busy?'Please wait':progress>0?`${Math.max(1,Math.ceil(3-progress*3))}s remaining`:disabled?'Choose a reason first':'Press and hold'}</span>
      </button>
    </div>
    <p id="dismiss-hold-help" role="status" className="text-xs text-[#94a3b8]">{busy?'Saving dismissal…':progress>0?'Keep holding. Release to cancel.':disabled?'Select a reason above to unlock dismissal.':'Hold for 3 seconds. Release to cancel.'}</p>
    {error&&<p role="alert" className="text-sm text-red-200">{error}</p>}
  </div>;
}

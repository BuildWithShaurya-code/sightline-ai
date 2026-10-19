import {useEffect,useRef,useState} from 'react';
import {MaterialIcon} from './MaterialIcon.tsx';
import {SlideGesture} from '../../services/slideGesture.ts';

export function FalseAlarmSlider({onComplete,disabled=false}:{onComplete:()=>Promise<void>;disabled?:boolean}){
  const track=useRef<HTMLDivElement>(null),gesture=useRef(new SlideGesture()),running=useRef(false),mounted=useRef(true),lastPointer=useRef(-Infinity);
  const [progress,setProgress]=useState(0),[dragging,setDragging]=useState(false),[busy,setBusy]=useState(false),[error,setError]=useState<string|null>(null);
  const travel=()=>Math.max(1,(track.current?.clientWidth||56)-56);
  const reset=()=>{gesture.current.cancel();setDragging(false);setProgress(0);};
  useEffect(()=>{
    mounted.current=true;const blur=()=>reset(),visibility=()=>{if(document.hidden)reset();};
    window.addEventListener('blur',blur);document.addEventListener('visibilitychange',visibility);
    return()=>{mounted.current=false;gesture.current.cancel();window.removeEventListener('blur',blur);document.removeEventListener('visibilitychange',visibility);};
  },[]);
  useEffect(()=>{if(disabled)reset();},[disabled]);
  async function complete(){
    if(disabled||running.current)return;
    running.current=true;setBusy(true);setError(null);reset();
    try{await onComplete();}
    catch(e){if(mounted.current)setError(e instanceof Error?e.message:'Could not open dismissal confirmation. Please retry.');}
    finally{running.current=false;if(mounted.current)setBusy(false);}
  }
  return <div className="w-full flex flex-col gap-2">
    <div ref={track} role="slider" tabIndex={disabled||busy?-1:0} aria-label="Slide to dismiss false alarm" aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(progress*100)} aria-disabled={disabled||busy} aria-valuetext={busy?'Opening dismissal confirmation':'Slide, tap, or press Enter to open dismissal confirmation'}
      onPointerDown={e=>{
        if(disabled||running.current||(e.pointerType==='mouse'&&e.button!==0))return;
        e.preventDefault();
        if(!gesture.current.start(e.pointerId,e.clientX,travel()))return;
        e.currentTarget.setPointerCapture(e.pointerId);setDragging(true);
      }}
      onPointerMove={e=>{if(gesture.current.move(e.pointerId,e.clientX))setProgress(gesture.current.progress);}}
      onPointerUp={e=>{
        const result=gesture.current.finish(e.pointerId,e.clientX);if(!result)return;
        lastPointer.current=performance.now();setDragging(false);setProgress(0);
        if(e.currentTarget.hasPointerCapture(e.pointerId))e.currentTarget.releasePointerCapture(e.pointerId);
        if(result==='tap'||result==='complete')void complete();
      }}
      onPointerCancel={()=>{lastPointer.current=performance.now();reset();}}
      onLostPointerCapture={()=>{if(dragging)reset();}}
      onClick={()=>{if(performance.now()-lastPointer.current>500)void complete();}}
      onBlur={reset}
      onKeyDown={e=>{
        if(disabled||busy)return;
        if(['Enter',' ','End'].includes(e.key)){e.preventDefault();void complete();}
        else if(['ArrowRight','ArrowUp','ArrowLeft','ArrowDown','Home','Escape'].includes(e.key)){
          e.preventDefault();if(e.key==='Home'||e.key==='Escape'){reset();return;}
          const done=gesture.current.step(['ArrowRight','ArrowUp'].includes(e.key)?.25:-.25);setProgress(gesture.current.progress);if(done)void complete();
        }
      }}
      className={`relative w-full h-14 rounded-full bg-[#122131] border border-[#273647] overflow-hidden select-none touch-none ${disabled?'opacity-50':busy?'cursor-wait':'cursor-pointer'}`}>
      <span className="absolute inset-0 flex items-center justify-center pl-12 pr-4 text-xs font-semibold text-[#d4e4fa] pointer-events-none" style={{opacity:busy?1:Math.max(0,1-progress*1.6)}}>{busy?'Opening confirmation…':'Slide or tap to dismiss'}{!busy&&<MaterialIcon name="chevron_right" className="text-base ml-1"/>}</span>
      <span className="absolute left-1 top-1 w-12 h-12 rounded-full bg-gradient-to-br from-red-500 to-rose-700 text-white flex items-center justify-center pointer-events-none" style={{transform:`translateX(${progress*travel()}px)`,transition:dragging?'none':'transform 160ms cubic-bezier(.2,.8,.2,1)'}}><MaterialIcon name={busy?'sync':'close'} className={`text-[22px] ${busy?'animate-spin':''}`}/></span>
    </div>
    {error&&<p role="alert" className="text-xs text-red-200">{error}</p>}
  </div>;
}

import {useRef,useState} from 'react';
import {MaterialIcon} from './MaterialIcon.tsx';

export function SignInSlider({pending,unlocked,onComplete}:{pending:boolean;unlocked:boolean;onComplete:()=>Promise<boolean>}) {
  const [progress,setProgress]=useState(0),[dragging,setDragging]=useState(false);
  const gesture=useRef<{pointer:number;start:number;travel:number;progress:number}|null>(null);
  const track=useRef<HTMLDivElement>(null),value=useRef(0),busy=useRef(false);
  const move=(next:number)=>{value.current=Math.max(0,Math.min(1,next));setProgress(value.current);};
  const reset=()=>{gesture.current=null;setDragging(false);move(0);};
  async function complete(){
    if(busy.current||pending||unlocked)return;
    busy.current=true;move(1);
    try{if(!await onComplete())move(0);}finally{busy.current=false;}
  }
  const shown=pending||unlocked?1:progress;
  return <div ref={track} role="slider" tabIndex={pending||unlocked?-1:0} aria-label="Slide to authenticate" aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(shown*100)} aria-valuetext={pending?'Signing in':unlocked?'Signed in':`${Math.round(shown*100)}% — slide right, or press Enter to sign in`} aria-disabled={pending||unlocked}
    onKeyDown={e=>{
      if(pending||unlocked)return;
      if(['ArrowRight','ArrowUp','ArrowLeft','ArrowDown','Home','End','Enter',' ','Escape'].includes(e.key))e.preventDefault();
      if(e.key==='Enter'||e.key===' '||e.key==='End')void complete();
      else if(e.key==='ArrowRight'||e.key==='ArrowUp'){move(value.current+.2);if(value.current>=.88)void complete();}
      else if(e.key==='ArrowLeft'||e.key==='ArrowDown')move(value.current-.2);
      else if(e.key==='Home'||e.key==='Escape')reset();
    }}
    onBlur={()=>{if(!busy.current)reset();}}
    className={`signin-slider relative h-16 rounded-full border overflow-hidden select-none ${dragging?'border-[#4edea3]':'border-[#4edea3]/30'} ${unlocked?'bg-[#4edea3] border-[#4edea3]':'bg-[#051424]'} ${pending?'cursor-wait':''}`}
    style={{'--slide-progress':shown,'--slide-transition':dragging?'none':'transform 380ms cubic-bezier(.2,.8,.2,1)'} as React.CSSProperties}>
    <div className="signin-slider-fill absolute inset-1 rounded-full bg-[#4edea3]/15 pointer-events-none"/>
    <div className={`absolute inset-0 flex items-center justify-center pointer-events-none ${pending||unlocked?'pr-12 pl-3':'pl-10 pr-3'}`}><span role="status" aria-live="polite" className={`text-sm font-semibold transition-colors ${unlocked?'text-[#003824]':'text-[#4edea3]'}`} style={{opacity:pending||unlocked?1:Math.max(0,1-shown*2)}}>{pending?'Signing in…':unlocked?'Signed in':'Slide to sign in'}{!pending&&!unlocked&&<span className="inline-flex align-middle ml-2 text-[#4edea3]/60"><MaterialIcon name="keyboard_double_arrow_right" className="text-lg"/></span>}</span></div>
    <div className="signin-slider-thumb absolute left-1.5 top-1.5 h-[50px] w-[50px] rounded-full bg-[#4edea3] text-[#003824] flex items-center justify-center shadow-[0_2px_8px_#0003] cursor-grab active:cursor-grabbing touch-none"
      onPointerDown={e=>{
        if(pending||unlocked||busy.current||e.button!==0)return;
        e.preventDefault();e.currentTarget.setPointerCapture(e.pointerId);
        gesture.current={pointer:e.pointerId,start:e.clientX,travel:Math.max(1,(track.current?.clientWidth||64)-62),progress:value.current};setDragging(true);
      }}
      onPointerMove={e=>{const g=gesture.current;if(g&&g.pointer===e.pointerId)move(g.progress+(e.clientX-g.start)/g.travel);}}
      onPointerUp={e=>{if(gesture.current?.pointer!==e.pointerId)return;gesture.current=null;setDragging(false);if(value.current>=.88)void complete();else move(0);}}
      onPointerCancel={reset} onLostPointerCapture={()=>{if(gesture.current)reset();}}>
      <MaterialIcon name={pending?'sync':unlocked?'check':'arrow_forward'} className={`text-[22px] ${pending?'animate-spin':''}`}/>
    </div>
  </div>;
}

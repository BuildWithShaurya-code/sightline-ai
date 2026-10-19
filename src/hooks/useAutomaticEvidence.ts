import {useEffect,useRef,useState} from 'react';
import type {FramePrediction} from './useFrameDetection.ts';
import type {Incident} from '../types/sightline.ts';
import {saveAutomaticEvidence} from '../services/api.ts';

export interface EvidenceCapture {sample:FramePrediction;save:()=>Promise<Incident>;}
type SavingCapture={sample:FramePrediction;result:Promise<Incident>;failed:boolean;session:string;offset:number};

export function useAutomaticEvidence(prediction: FramePrediction|null, source: string|null, enabled: boolean) {
  const [incident,setIncident]=useState<Incident|null>(null),[saving,setSaving]=useState(false),[error,setError]=useState(''),[attempt,setAttempt]=useState(0);
  const generation=useRef(0),count=useRef(0),busy=useRef(false),frozen=useRef(false),transferred=useRef(false);
  const session=useRef(''),firstTime=useRef<number|null>(null),previous=useRef<Blob|null>(null),pending=useRef<FramePrediction|null>(null);
  const controller=useRef<AbortController|null>(null),capture=useRef<SavingCapture|null>(null);
  useEffect(()=>{
    generation.current++;if(!transferred.current)controller.current?.abort();
    count.current=0;busy.current=false;frozen.current=false;transferred.current=false;capture.current=null;
    session.current=crypto.randomUUID();firstTime.current=null;previous.current=null;pending.current=null;
    setIncident(null);setError('');setSaving(false);
    return()=>{generation.current++;if(!transferred.current)controller.current?.abort();};
  },[source,enabled]);
  useEffect(()=>{
    if(!enabled||!source||frozen.current||busy.current||count.current>=3)return;
    const sample=prediction?.response.detections.some(d=>d.classId==='mask'&&d.confidence>=.25)?prediction:pending.current;
    if(!sample?.image||sample.image===previous.current)return;
    const version=generation.current;
    pending.current=sample;busy.current=true;setSaving(true);setError('');firstTime.current??=sample.sourceTime;
    const request=new AbortController();controller.current=request;
    const offset=Math.max(0,sample.sourceTime-firstTime.current),episode=session.current;
    const result=saveAutomaticEvidence(sample.image,episode,offset,{signal:request.signal});
    const current:SavingCapture={sample,result,failed:false,session:episode,offset};capture.current=current;
    void result.then(saved=>{
      if(version===generation.current){setIncident(saved);count.current=saved.frames.length;previous.current=sample.image;pending.current=null;}
    },e=>{
      current.failed=true;
      if(version===generation.current)setError(e instanceof Error?e.message:'Automatic evidence could not be saved.');
    }).finally(()=>{if(version===generation.current){busy.current=false;setSaving(false);}});
  },[prediction,source,enabled,attempt]);
  function transfer():EvidenceCapture {
    const current=capture.current;
    if(!current)throw new Error('The camera is preparing a photo. Please try again.');
    frozen.current=true;transferred.current=true;controller.current=null;
    let first=true;
    return {sample:current.sample,save:()=>{
      if(first){first=false;if(!current.failed)return current.result;}
      // Retry the same exact capture/episode, not a later camera frame.
      return saveAutomaticEvidence(current.sample.image,current.session,current.offset);
    }};
  }
  return {incident,saving,error,canConfirm:Boolean(incident||capture.current),transfer,retry:()=>setAttempt(x=>x+1),freeze:()=>{frozen.current=true;}};
}

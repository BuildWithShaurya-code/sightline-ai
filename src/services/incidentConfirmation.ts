import type {Incident} from '../types/sightline.ts';
import type {EvidenceCapture} from '../hooks/useAutomaticEvidence.ts';
import {getCurrentAccountId} from './auth.ts';
import {getCachedIncident,reviewIncident} from './api.ts';

type ConfirmationTask={owner:string;routeId:string;incident:Incident;previewOnly:boolean;result:Promise<Incident>;retry:()=>Promise<Incident>;previewUrl?:string};
let active:ConfirmationTask|null=null;
function dispose(task:ConfirmationTask|null){if(task?.previewUrl)URL.revokeObjectURL(task.previewUrl);}
export function clearIncidentConfirmation(){dispose(active);active=null;}
export function pendingIncidentConfirmation(id?:string|null):ConfirmationTask|null {
  if(active&&active.owner!==getCurrentAccountId())clearIncidentConfirmation();
  return active?.routeId===id?active:null;
}
function createTask(owner:string,routeId:string,incident:Incident,previewOnly:boolean,operation:()=>Promise<Incident>,previewUrl?:string):ConfirmationTask {
  clearIncidentConfirmation();
  const task:ConfirmationTask={owner,routeId,incident:structuredClone(incident),previewOnly,result:Promise.resolve(incident),retry:()=>Promise.resolve(incident),previewUrl};
  task.retry=()=>{
    task.result=(async()=>{
      if(owner!==getCurrentAccountId())throw new Error('Account changed. Open the alert from your history.');
      const saved=await operation();
      if(owner!==getCurrentAccountId())throw new Error('Account changed. Open the alert from your history.');
      if(saved.status!=='confirmed')throw new Error('The threat confirmation could not be verified. Please retry.');
      return saved;
    })();
    void task.result.catch(()=>{});return task.result;
  };
  active=task;task.retry();return task;
}
/** Existing persisted photos can open without waiting for the review write. */
export function beginIncidentConfirmation(id:string,fallback?:Incident|null):ConfirmationTask {
  const existing=pendingIncidentConfirmation(id);if(existing)return existing;
  const owner=getCurrentAccountId(),incident=getCachedIncident(id)||(fallback?.id===id?fallback:null);
  if(!owner||!incident)throw new Error('The saved evidence is not ready yet. Please retry.');
  return createTask(owner,id,incident,false,async()=>{
    const saved=await reviewIncident(id,'confirmed','Threat confirmed by the operator from the detection warning.');
    if(saved.id!==id)throw new Error('The threat confirmation could not be verified. Please retry.');
    return saved;
  });
}
/** A real camera photo is available locally before its upload finishes. Never label this preview saved. */
export function beginCaptureConfirmation(capture:EvidenceCapture):ConfirmationTask {
  const owner=getCurrentAccountId();if(!owner)throw new Error('Sign in before confirming an alert.');
  const routeId='PENDING-'+crypto.randomUUID(),previewUrl=URL.createObjectURL(capture.sample.image);
  const incident:Incident={id:routeId,sourceId:'Camera capture',createdAt:new Date().toISOString(),status:'unreviewed',title:'Captured mask preview',channel:'LIVE CAMERA',frames:[{id:'local-capture',timeSeconds:0,imageDataUrl:previewUrl}],detections:capture.sample.response.detections.map(d=>({...d,evidence_id:'local-capture'}))};
  return createTask(owner,routeId,incident,true,async()=>{
    const saved=await capture.save();
    if(owner!==getCurrentAccountId())throw new Error('Account changed. Open the alert from your history.');
    const confirmed=await reviewIncident(saved.id,'confirmed','Threat confirmed by the operator from the detection warning.');
    if(confirmed.id!==saved.id)throw new Error('The threat confirmation could not be verified. Please retry.');
    return confirmed;
  },previewUrl);
}
export function finishIncidentConfirmation(task:ConfirmationTask){
  if(active===task)active=null;
  // Allow React to switch from the preview to the persisted image before releasing its URL.
  if(task.previewUrl)setTimeout(()=>dispose(task),1000);
}

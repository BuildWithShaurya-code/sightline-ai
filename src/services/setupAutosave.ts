export type AutosaveState = {status:'idle'|'waiting'|'saving'|'saved'|'error'; error?:string};
/** Debounces valid drafts, serializes writes, and never acknowledges a stale revision. */
export function createSetupAutosave<T>(save:(value:T)=>Promise<unknown>,notify:(state:AutosaveState)=>void,delay=800) {
  let timer:ReturnType<typeof setTimeout>|undefined, pending:{value:T;revision:number}|null=null;
  let running:Promise<void>|null=null,revision=0,alive=true,lastSaved='',inFlight='';
  const key=(value:T)=>JSON.stringify(value);
  const emit=(state:AutosaveState)=>{if(alive)notify(state);};
  const clear=()=>{if(timer!==undefined)clearTimeout(timer);timer=undefined;};
  function drain():Promise<void> {
    if(running)return running.then(()=>pending?drain():undefined);
    running=(async()=>{
      while(alive&&pending){
        const job=pending;pending=null;inFlight=key(job.value);emit({status:'saving'});
        try {
          await save(job.value);lastSaved=key(job.value);
          if(alive&&revision===job.revision)emit({status:'saved'});
        } catch(e) {
          if(alive&&revision===job.revision)emit({status:'error',error:e instanceof Error?e.message:'Details were not saved. Please retry.'});
        }
      }
    })().finally(()=>{running=null;inFlight='';});
    return running;
  }
  return {
    prime(value:T){lastSaved=key(value);emit({status:'saved'});},
    schedule(value:T){
      clear();const next=++revision;
      if(!running&&key(value)===lastSaved){pending=null;emit({status:'saved'});return;}
      pending={value,revision:next};emit({status:'waiting'});
      timer=setTimeout(()=>{timer=undefined;void drain();},delay);
    },
    invalidate(){clear();pending=null;++revision;emit({status:'idle'});},
    async flush(value:T){
      clear();const target=key(value);
      if(running&&inFlight===target&&!pending){await running;return alive&&lastSaved===target;}
      if(!running&&lastSaved===target){emit({status:'saved'});return alive;}
      pending={value,revision:++revision};await drain();return alive&&lastSaved===target;
    },
    dispose(){alive=false;clear();pending=null;++revision;}
  };
}

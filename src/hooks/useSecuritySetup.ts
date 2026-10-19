import {useEffect,useState} from 'react';
import {supabase} from '../services/auth.ts';
import {createSecuritySetupStore} from '../services/securitySetupStore.ts';
import type {SecuritySetup} from '../services/securitySetup.ts';
export const securitySetupStore=createSecuritySetupStore(supabase);
export function useSecuritySetup() {
  const [details,setDetails]=useState<SecuritySetup|null>(null),[loading,setLoading]=useState(true),[error,setError]=useState('');
  const [accountRevision,setAccountRevision]=useState(0),[ownerId,setOwnerId]=useState<string|null>(null);
  useEffect(()=>{
    let alive=true,revision=0,owner:string|null|undefined=undefined;
    const load=async()=>{const request=++revision;setDetails(null);setLoading(true);setError('');try{const data=await securitySetupStore.load();if(alive&&request===revision)setDetails(data);}catch(e){if(alive&&request===revision)setError(e instanceof Error?e.message:'Could not load security details.');}finally{if(alive&&request===revision)setLoading(false);}};
    void load();
    const subscription=supabase?.auth.onAuthStateChange((_event,session)=>{const id=session?.user.id||null;setOwnerId(id);if(owner!==undefined&&id!==owner){++revision;setDetails(null);setError('');setAccountRevision(n=>n+1);void Promise.resolve().then(load);}owner=id;});
    return()=>{alive=false;++revision;subscription?.data.subscription.unsubscribe();};
  },[]);
  return {details,loading,error,accountRevision,ownerId};
}

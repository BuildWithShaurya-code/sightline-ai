import type {SupabaseClient} from '@supabase/supabase-js';
import {validateSecuritySetup,type SecuritySetup} from './securitySetup.ts';
export const SETUP_UNAVAILABLE='Private account saving is not connected on this installation. Your details have not been saved. Ask your administrator to enable account storage.';
/** Uses the SDK session for UI binding and server-enforced RLS for every read/write. Never uses the legacy demo token, SQLite contacts, or browser persistence. */
export function createSecuritySetupStore(client:SupabaseClient|null) {
  async function owner() {
    if(!client)throw new Error(SETUP_UNAVAILABLE);
    const {data,error}=await client.auth.getSession();
    if(error||!data.session?.user||!data.session.expires_at||data.session.expires_at*1000<=Date.now())throw new Error('Your session has ended. Sign in again to save your details securely.');
    return data.session.user.id;
  }
  async function assertOwner(expected:string){if(await owner()!==expected)throw new Error('Account changed. Reload the form before continuing.');}
  function stored(value:unknown):SecuritySetup {
    if(!value||typeof value!=='object')throw new Error('Saved security details are invalid. Please update them.');
    const check=validateSecuritySetup(value as SecuritySetup);
    if(Object.keys(check.errors).length)throw new Error('Saved security details are incomplete. Please update them.');
    return check.data;
  }
  return {
    async load():Promise<SecuritySetup|null> {
      const id=await owner();
      const {data,error}=await client!.from('security_settings').select('details').eq('user_id',id).maybeSingle();
      if(error)throw new Error('Could not load private security details. Check your connection or ask your administrator to check account storage.');
      await assertOwner(id);return data?stored(data.details):null;
    },
    async save(input:SecuritySetup,expectedOwner?:string):Promise<SecuritySetup> {
      const checked=validateSecuritySetup(input);if(Object.keys(checked.errors).length)throw new Error('Please correct the highlighted fields.');
      const id=await owner();
      if(expectedOwner&&id!==expectedOwner)throw new Error('Account changed. Reload the form before continuing.');
      const {data,error}=await client!.from('security_settings').upsert({user_id:id,details:checked.data},{onConflict:'user_id'}).select('details').single();
      if(error)throw new Error('Details were not saved. Check your connection and private account storage, then try again.');
      await assertOwner(id);if(!data)throw new Error('The saved details could not be verified. Please retry.');return stored(data.details);
    }
  };
}

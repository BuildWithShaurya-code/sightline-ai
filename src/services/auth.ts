/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */

import { createClient, SupabaseClient, type Session } from '@supabase/supabase-js';

const AUTH_STORAGE_KEY = 'sightline_auth_session';
export interface StoredSession {
  operatorId: string;
  token: string;
  email?: string;
  username?: string;
  createdAt: string;
}

// Optional Supabase Client initialization
const supabaseUrl = import.meta.env.VITE_SUPABASE_URL;
const supabaseKey = import.meta.env.VITE_SUPABASE_PUBLISHABLE_KEY;

export const supabase: SupabaseClient | null =
  typeof supabaseUrl === 'string' &&
  typeof supabaseKey === 'string' &&
  supabaseUrl.trim().length > 0 &&
  supabaseKey.trim().length > 0
    ? createClient(supabaseUrl.trim(), supabaseKey.trim(), {
        global: {fetch:(input,init)=>{
          const timeout=AbortSignal.timeout(15000);
          return fetch(input,{...init,signal:init?.signal?AbortSignal.any([init.signal,timeout]):timeout});
        }},
        auth: {
          persistSession: true,
          autoRefreshToken: true,
        },
      })
    : null;

// UI identity follows the real account session, never a legacy demo token.
let connectedUserId: string | null = null;
export function getCurrentAccountId():string|null {return connectedUserId;}
function accountSession(session: Session): StoredSession {
  const email = session.user.email || '';
  const prior=getStoredSession();
  const requestedName=session.user.user_metadata?.username;
  // A display label only. Authorization always uses the provider's verified user ID.
  const username=(prior?.email===email?prior.username:undefined)||(typeof requestedName==='string'?requestedName:undefined);
  return {operatorId: username || email.split('@')[0] || 'Account', username, email, token: session.access_token, createdAt: new Date().toISOString()};
}
function clearStoredSession() {
  try {sessionStorage.removeItem(AUTH_STORAGE_KEY); localStorage.removeItem(AUTH_STORAGE_KEY);} catch { /* Storage may be disabled. */ }
}
export async function restoreSession(): Promise<boolean> {
  if (!supabase) return Boolean(getStoredSession());
  try {
    const {data} = await supabase.auth.getSession();
    if(!data.session){connectedUserId=null;clearStoredSession();return false;}
    const {data: identity, error} = await supabase.auth.getUser();
    if (error || !identity.user || !data.session || data.session.user.id !== identity.user.id) {
      connectedUserId = null; clearStoredSession(); return false;
    }
    connectedUserId = identity.user.id;
    saveSession(accountSession(data.session), !sessionStorage.getItem(AUTH_STORAGE_KEY));
    void hydrateAccountUsername(data.session);
    return true;
  } catch {connectedUserId = null; clearStoredSession(); return false;}
}

/**
 * Returns current authenticated session from storage or null.
 */
export function getStoredSession(): StoredSession | null {
  try {
    const raw =
      sessionStorage.getItem(AUTH_STORAGE_KEY) || localStorage.getItem(AUTH_STORAGE_KEY);
    if (raw) {
      const parsed = JSON.parse(raw);
      if (typeof parsed.operatorId === 'string' && typeof parsed.token === 'string') {
        return parsed as StoredSession;
      }
    }
  } catch {
    // fallback
  }
  return null;
}

/**
 * Checks whether an operator is authenticated.
 */
export function isAuthenticated(): boolean {
  return supabase ? connectedUserId !== null : Boolean(getStoredSession());
}

/**
 * Returns current authenticated operator info or null.
 */
export function getCurrentOperator(): { operatorId: string; email?: string } | null {
  const session = getStoredSession();
  if (session) {
    return {
      operatorId: session.operatorId,
      email: session.email?.endsWith('@accounts.sightline.invalid')?undefined:session.email,
    };
  }
  return null;
}

/**
 * Retrieves the active Bearer access token for API requests.
 */
export async function getAccessToken(): Promise<string | null> {
  if (supabase) {
    try {
      const { data, error } = await supabase.auth.getSession();
      return error ? null : data.session?.access_token || null;
    } catch { return null; }
  }
  return getStoredSession()?.token || null;
}

/**
 * Authenticates an operator session via Supabase or backend endpoint.
 */
export async function login(
  operatorId: string,
  passcode: string,
  rememberSession = true
): Promise<{ success: boolean; error?: string }> {
  const trimmedId = operatorId.trim();
  const trimmedPass = passcode.trim();

  if (!trimmedId) {
    return { success: false, error: 'Enter your username.' };
  }
  if (!trimmedPass) {
    return { success: false, error: 'Enter your password.' };
  }
  if (trimmedPass.length < 4) {
    return { success: false, error: 'Password must be at least 4 characters.' };
  }

  // A configured account provider must never fall through to demo authentication.
  if (supabase) {
    try {
      let outcome;
      if(trimmedId.includes('@')) outcome=await supabase.auth.signInWithPassword({ email: trimmedId, password: passcode });
      else {
        const response=await fetch('/api/v1/auth/username-login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({username:trimmedId,password:passcode}),cache:'no-store',signal:AbortSignal.timeout(15000)});
        const result=await response.json().catch(()=>null);
        if(!response.ok)return {success:false,error:result?.message||'Username or password is incorrect. Please try again.'};
        if(!result?.access_token||!result?.refresh_token)return {success:false,error:'Could not verify account sign-in.'};
        outcome=await supabase.auth.setSession({access_token:result.access_token,refresh_token:result.refresh_token});
      }
      const {data,error}=outcome;
      if (error || !data.session) return { success: false, error: error?.code === 'email_not_confirmed' ? 'Sign in with the username you created to activate this account. No confirmation email is needed.' : error?.code === 'invalid_credentials' ? 'Username or password is incorrect. New here? Choose Create account first.' : 'Could not sign in to your account. Check your details and connection, then try again.' };
      connectedUserId = data.session.user.id;
      saveSession(accountSession(data.session), rememberSession);
      void hydrateAccountUsername(data.session);
      notifyAuthListeners(true);
      return { success: true };
    } catch {
      return { success: false, error: 'Could not reach account sign-in. Check your connection and try again.' };
    }
  }

  return {success:false,error:'Account sign-in is not connected. Please contact the site owner.'};
}

export interface RegistrationInput {username:string;password:string;confirmPassword:string}
export type RegistrationErrors=Partial<Record<keyof RegistrationInput,string>>;
export function validateRegistration(input:RegistrationInput):RegistrationErrors {
  const errors:RegistrationErrors={};
  if(!/^[a-z0-9][a-z0-9_. -]{2,31}$/.test(input.username.trim().toLowerCase()))errors.username='Use 3–32 letters or numbers. Spaces, dots, underscores and hyphens are also allowed.';
  if(input.password.length<8||new TextEncoder().encode(input.password).length>72)errors.password='Use at least 8 characters. Very long passwords must fit within 72 bytes.';
  if(input.password!==input.confirmPassword)errors.confirmPassword='The passwords do not match.';
  return errors;
}
export async function register(input:RegistrationInput,remember=true):Promise<{success:boolean;error?:string}>{
  if(Object.keys(validateRegistration(input)).length)return {success:false,error:'Please correct the highlighted fields.'};
  if(!supabase)return {success:false,error:'Account creation is not connected. Please contact the site owner.'};
  try{
    const response=await fetch('/api/v1/auth/register',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({username:input.username.trim().toLowerCase(),password:input.password}),cache:'no-store',signal:AbortSignal.timeout(30000)});
    const result=await response.json().catch(()=>null);
    if(!response.ok)return {success:false,error:result?.message||'Could not create this account. Please try signing in or choose another username.'};
    if(!result?.access_token||!result?.refresh_token)return {success:false,error:'The new account session could not be verified. Try signing in.'};
    const {data,error}=await supabase.auth.setSession({access_token:result.access_token,refresh_token:result.refresh_token});
    if(error||!data.session)return {success:false,error:'Your account was created, but sign-in could not finish. Sign in using your username and password.'};
    connectedUserId=data.session.user.id;saveSession(accountSession(data.session),remember);notifyAuthListeners(true);return {success:true};
  }catch{return {success:false,error:'Could not reach account creation. Please retry or sign in if your account was already created.'};}
}

function saveSession(session: StoredSession, remember: boolean): void {
  try {
    sessionStorage.removeItem(AUTH_STORAGE_KEY);
    localStorage.removeItem(AUTH_STORAGE_KEY);

    if (remember) {
      localStorage.setItem(AUTH_STORAGE_KEY, JSON.stringify(session));
    } else {
      sessionStorage.setItem(AUTH_STORAGE_KEY, JSON.stringify(session));
    }
  } catch (err) {
    console.warn('Failed to save session:', err);
  }
}

/**
 * Logs out the active operator and purges credentials.
 */
export async function logout(): Promise<void> {
  connectedUserId = null;
  clearStoredSession();
  notifyAuthListeners(false);
  if (supabase) {
    try {
      await supabase.auth.signOut();
    } catch {
      // ignore
    }
  }

  try {
    sessionStorage.removeItem(AUTH_STORAGE_KEY);
    localStorage.removeItem(AUTH_STORAGE_KEY);
  } catch (err) {
    console.warn('Logout error:', err);
  }

  notifyAuthListeners(false);
}

// Simple event subscription for auth state changes
type AuthListener = (loggedIn: boolean) => void;
const authListeners = new Set<AuthListener>();

export function onAuthStateChange(listener: AuthListener): () => void {
  authListeners.add(listener);
  return () => {
    authListeners.delete(listener);
  };
}

function notifyAuthListeners(loggedIn: boolean) {
  authListeners.forEach((fn) => {
    try {
      fn(loggedIn);
    } catch {
      // ignore
    }
  });
}

// Keep tabs, token refreshes and sign-out synchronized with the account provider.
supabase?.auth.onAuthStateChange((_event, session) => {
  connectedUserId = session?.user.id || null;
  if (session) saveSession(accountSession(session), !sessionStorage.getItem(AUTH_STORAGE_KEY));
  else clearStoredSession();
  notifyAuthListeners(Boolean(session));
});

async function usernameRequest(method:'GET'|'PUT',username?:string,expectedOwner?:string):Promise<string|null>{
  const {data}=await supabase!.auth.getSession();
  if(!data.session)throw new Error('Sign in to manage your account.');
  if(expectedOwner&&data.session.user.id!==expectedOwner)throw new Error('Account changed. Reopen account settings.');
  const token=data.session.access_token;
  const response=await fetch('/api/v1/auth/username',{method,headers:{Authorization:`Bearer ${token}`,...(method==='PUT'?{'Content-Type':'application/json'}:{})},body:method==='PUT'?JSON.stringify({username}):undefined,cache:'no-store',signal:AbortSignal.timeout(method==='GET'?5000:15000)});
  const result=await response.json().catch(()=>null);
  if(!response.ok)throw new Error(result?.message||'Could not load account settings. Please retry.');
  return typeof result?.username==='string'?result.username:null;
}
async function hydrateAccountUsername(session:Session){
  try{
    const name=await usernameRequest('GET');
    const {data}=await supabase!.auth.getSession();
    if(data.session?.user.id!==session.user.id)return;
    saveSession({...accountSession(session),username:name||undefined,operatorId:name||session.user.email?.split('@')[0]||'Account'},!sessionStorage.getItem(AUTH_STORAGE_KEY));
  }catch{ /* Username availability must not block email sign-in. */ }
}
export const loadAccountUsername=()=>usernameRequest('GET');
export async function saveAccountUsername(value:string,expectedOwner:string){
  const name=await usernameRequest('PUT',value,expectedOwner);
  const {data}=await supabase!.auth.getSession();
  if(!data.session)throw new Error('Your session has ended. Sign in again.');
  await hydrateAccountUsername(data.session);return name;
}
export async function changeAccountPassword(currentPassword:string,newPassword:string,expectedOwner:string){
  if(!supabase)throw new Error('Account saving is not connected.');
  const {data:identity,error:identityError}=await supabase.auth.getUser();
  if(identityError||!identity.user?.email||identity.user.id!==expectedOwner)throw new Error('Your account changed or session has ended. Sign in again.');
  // Isolated reauthentication never replaces another tab's currently signed-in account.
  const verifier=createClient(supabaseUrl,supabaseKey,{auth:{persistSession:false,autoRefreshToken:false,detectSessionInUrl:false}});
  try{
    const {data,error}=await verifier.auth.signInWithPassword({email:identity.user.email,password:currentPassword});
    if(error||data.user?.id!==expectedOwner)throw new Error('Your current password is incorrect.');
    const updated=await verifier.auth.updateUser({password:newPassword,current_password:currentPassword});
    if(updated.error)throw new Error(updated.error.message||'Your password was not changed. Please retry.');
    if(updated.data.user?.id!==expectedOwner)throw new Error('The password change could not be verified.');
  } finally {await verifier.auth.signOut({scope:'local'}).catch(()=>{});}
}

/** Owner-bound PIN operations use the captured provider token, never a local/demo token. */
async function securityPinRequest(expectedOwner:string,pin?:string,currentPin?:string){
  if(!supabase)throw new Error('Sign in to manage your security PIN.');
  const {data}=await supabase.auth.getSession();
  if(!data.session||data.session.user.id!==expectedOwner)throw new Error('Account changed. Reopen Account settings.');
  const response=await fetch('/api/v1/dispatches/security/pin',{method:pin===undefined?'GET':'POST',headers:{Authorization:`Bearer ${data.session.access_token}`,'X-Expected-Owner':expectedOwner,'Content-Type':'application/json'},body:pin===undefined?undefined:JSON.stringify({pin,...(currentPin?{currentPin}:{})}),cache:'no-store',signal:AbortSignal.timeout(15000)});
  const result=await response.json().catch(()=>null);
  if(!response.ok)throw new Error(result?.message||'Your security PIN was not saved. Please retry.');
  const latest=await supabase.auth.getSession();
  if(latest.data.session?.user.id!==expectedOwner)throw new Error('Account changed. Reopen Account settings.');
  return result;
}
export async function loadSecurityPinStatus(owner:string):Promise<boolean>{
  const result=await securityPinRequest(owner);
  if(typeof result?.configured!=='boolean')throw new Error('Could not check your security PIN.');
  return result.configured;
}
export async function saveSecurityPin(owner:string,pin:string,currentPin?:string):Promise<void>{
  const result=await securityPinRequest(owner,pin,currentPin);
  if(result?.success!==true)throw new Error('Your security PIN could not be verified as saved.');
}

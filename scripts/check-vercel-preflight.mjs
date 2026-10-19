import assert from 'node:assert/strict';
import {checkVercelEnvironment, publicOrigin} from './vercel-preflight.mjs';
const valid = {VITE_API_URL:'https://api.sightline.ai',VITE_SUPABASE_URL:'https://fixture.supabase.co',VITE_SUPABASE_PUBLISHABLE_KEY:'sb_publishable_ISOLATED_TEST_VALUE'};
assert.equal(checkVercelEnvironment(valid).api,valid.VITE_API_URL);
for (const url of [undefined,'http://api.sightline.ai','https://localhost','https://127.0.0.1','https://[::1]','https://10.0.0.1','https://api.internal','https://api.sightline.ai:8443','https://api.sightline.ai/path','https://name:password@api.sightline.ai','https://api.sightline.ai/?token=private']) {
  assert.throws(()=>publicOrigin(url,'API'));
}
assert.throws(()=>checkVercelEnvironment({...valid,VITE_SUPABASE_PUBLISHABLE_KEY:'sb_secret_ISOLATED_TEST_VALUE'}));
assert.throws(()=>checkVercelEnvironment({...valid,VITE_SERVER_SECRET:'ISOLATED_TEST_VALUE'}));
assert.throws(()=>checkVercelEnvironment({...valid,VERCEL_URL:'api.sightline.ai'}));
console.log('Vercel preflight: 14 unsafe/missing configuration cases rejected; valid public settings accepted.');

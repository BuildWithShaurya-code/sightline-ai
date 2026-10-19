// Isolated username-only provider contract. No account/email is created.
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const root=path.resolve(__dirname,'..'),output=path.join(root,'qa/.signup-check.cjs');
const esbuild=require(path.join(root,'node_modules/esbuild'));
const storage=()=>{const m=new Map();return{getItem:k=>m.get(k)||null,setItem:(k,v)=>m.set(k,v),removeItem:k=>m.delete(k)}};
global.localStorage=storage();global.sessionStorage=storage();
let session=null,callback,providerError=null,lastInput=null,reads=0,lastRoute;
const user={id:'new-owner',email:'u-test@accounts.sightline.invalid',user_metadata:{username:'new_owner'}};
global.__signupClient={auth:{onAuthStateChange(fn){callback=fn;return{data:{subscription:{unsubscribe(){}}}}},getSession:async()=>({data:{session}}),getUser:async()=>{reads++;return{data:{user:session?.user||null},error:null}},setSession:async()=>{session={user,access_token:'isolated-access',refresh_token:'isolated-refresh'};callback('SIGNED_IN',session);return{data:{session},error:null}},signInWithPassword:async()=>{throw Error('Username signup must not require email')},signOut:async()=>{session=null;callback('SIGNED_OUT',null)}}};
global.fetch=async(url,init)=>{
 if(url==='/api/v1/auth/username')return new Promise(()=>{});
 lastRoute=url;lastInput=JSON.parse(init.body);
 return {ok:!providerError,json:async()=>providerError?{message:providerError}:{access_token:'isolated-access',refresh_token:'isolated-refresh'}};
};
(async()=>{
 await esbuild.build({entryPoints:[path.join(root,'src/services/auth.ts')],outfile:output,bundle:true,platform:'node',format:'cjs',define:{'import.meta.env':'{"VITE_SUPABASE_URL":"https://example.test","VITE_SUPABASE_PUBLISHABLE_KEY":"public-fixture-only"}'},plugins:[{name:'fake-provider',setup(b){b.onResolve({filter:/^@supabase\/supabase-js$/},()=>({path:'provider',namespace:'fake'}));b.onLoad({filter:/.*/,namespace:'fake'},()=>({contents:'export const createClient=()=>globalThis.__signupClient;',loader:'js'}));}}],logLevel:'silent'});
 const a=require(output),input={username:' New_Owner ',password:' exact password ',confirmPassword:' exact password '};
 assert.equal(await a.restoreSession(),false);assert.equal(reads,0);
 for(const username of ['123456','Jane Doe','  12 Jane Doe  ','test_user-42'])assert.equal(a.validateRegistration({...input,username}).username,undefined);
 for(const username of ['ab','name@example.com','name/other','name\tother','x'.repeat(33)])assert.ok(a.validateRegistration({...input,username}).username);
 assert.ok(a.validateRegistration({...input,password:'short'}).password);assert.ok(a.validateRegistration({...input,password:'😀'.repeat(19)}).password);assert.ok(a.validateRegistration({...input,confirmPassword:'different'}).confirmPassword);
 assert.equal((await a.register({...input,password:'short'})).success,false);assert.equal(lastInput,null);
 providerError='This username is already taken.';assert.equal((await a.register(input)).success,false);assert.equal(a.isAuthenticated(),false);providerError=null;
 assert.equal((await a.register(input)).success,true);assert.equal(lastRoute,'/api/v1/auth/register');assert.deepEqual(lastInput,{username:'new_owner',password:' exact password '});assert.equal(a.getCurrentOperator().operatorId,'new_owner');assert.equal(a.getCurrentOperator().email,undefined);assert.equal(a.isAuthenticated(),true);
 await a.logout();assert.equal(a.getCurrentAccountId(),null);
 console.log('PASS: unique username-only registration, no email payload, validation, duplicate rejection, exact passwords, real-session initialization and username display. Mock provider only.');
})().catch(e=>{console.error(e);process.exitCode=1}).finally(()=>fs.rmSync(output,{force:true}));

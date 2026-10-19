// Isolated SDK/HTTP contract checks. No real account or password is changed.
const assert=require('node:assert/strict'),path=require('node:path'),fs=require('node:fs');
const root=path.resolve(__dirname,'..'),out=path.join(root,'qa/.credentials-check.cjs'),esbuild=require(path.join(root,'node_modules/esbuild'));
const storage=()=>{const m=new Map();return {getItem:k=>m.get(k)||null,setItem:(k,v)=>m.set(k,v),removeItem:k=>m.delete(k),dump:()=>[...m.values()]}};global.localStorage=storage();global.sessionStorage=storage();
let callback,owner='owner-a',name='test_owner',failPassword=false,providerRejects=false,updated=0,temporarySignouts=0,demoCalls=0,receivedPassword;
const user=()=>({id:owner,email:'qa@example.test'}),session=()=>({user:user(),access_token:'test-access'});
const main={auth:{onAuthStateChange(fn){callback=fn;return {data:{subscription:{unsubscribe(){}}}}},getSession:async()=>({data:{session:session()},error:null}),getUser:async()=>({data:{user:user()},error:null}),setSession:async data=>{assert.equal(data.access_token,'test-access');callback('SIGNED_IN',session());return {data:{session:session()},error:null}},signOut:async()=>{},signInWithPassword:async()=>({data:{session:session()},error:null})}};
const isolated={auth:{signInWithPassword:async({password})=>{receivedPassword=password;return failPassword?{data:{user:null},error:{message:'wrong'}}:{data:{user:{id:'owner-a'}},error:null}},updateUser:async input=>{assert.equal(input.password,'isolated-new-password');assert.equal(input.current_password,'isolated-current-password');updated++;return providerRejects?{data:{user:null},error:{message:'Password policy rejected.'}}:{data:{user:{id:'owner-a'}},error:null}},signOut:async()=>{temporarySignouts++}}};
global.__makeAccountClient=(_url,_key,options)=>options.auth.persistSession===false?isolated:main;
global.fetch=async(url,options)=>{
 if(url==='/api/v1/auth/username-login'){const data=JSON.parse(options.body);assert.equal(data.username,'test_owner');assert.equal(data.password,' exact password ');return {ok:true,json:async()=>({access_token:'test-access',refresh_token:'test-refresh'})};}
 if(url==='/api/v1/auth/username'){assert.equal(options.headers.Authorization,'Bearer test-access');if(options.method==='PUT')name=JSON.parse(options.body).username;return {ok:true,json:async()=>({username:name})};}
 demoCalls++;throw Error('No demo path allowed');
};
(async()=>{
 await esbuild.build({entryPoints:[path.join(root,'src/services/auth.ts')],outfile:out,bundle:true,platform:'node',format:'cjs',define:{'import.meta.env':'{"VITE_SUPABASE_URL":"https://example.test","VITE_SUPABASE_PUBLISHABLE_KEY":"public-test-only"}'},plugins:[{name:'fake-account',setup(b){b.onResolve({filter:/^@supabase\/supabase-js$/},()=>({path:'account',namespace:'fake'}));b.onLoad({filter:/.*/,namespace:'fake'},()=>({contents:'export const createClient=(...args)=>globalThis.__makeAccountClient(...args);',loader:'js'}));}}],logLevel:'silent'});
 const auth=require(out);
 assert.equal((await auth.login('test_owner',' exact password ')).success,true);await new Promise(resolve=>setImmediate(resolve));assert.equal(auth.getCurrentOperator().operatorId,'test_owner');assert.equal(demoCalls,0);
 assert.equal(await auth.saveAccountUsername('changed_owner','owner-a'),'changed_owner');assert.equal(auth.getCurrentOperator().operatorId,'changed_owner');
 owner='owner-b';await assert.rejects(()=>auth.saveAccountUsername('must-not-write','owner-a'),/Account changed/);assert.equal(name,'changed_owner');await assert.rejects(()=>auth.changeAccountPassword('irrelevant','irrelevant','owner-a'),/account changed/);assert.equal(updated,0);owner='owner-a';
 failPassword=true;await assert.rejects(()=>auth.changeAccountPassword('wrong-current-password','isolated-new-password','owner-a'),/current password is incorrect/);assert.equal(updated,0);failPassword=false;
 providerRejects=true;await assert.rejects(()=>auth.changeAccountPassword('isolated-current-password','isolated-new-password','owner-a'),/policy rejected/);providerRejects=false;
 await auth.changeAccountPassword('isolated-current-password','isolated-new-password','owner-a');assert.equal(updated,2);assert.equal(temporarySignouts,3);assert.equal(receivedPassword,'isolated-current-password');assert.ok(!JSON.stringify([...localStorage.dump(),...sessionStorage.dump()]).includes('isolated-new-password'));
 console.log('PASS: username sign-in initializes a real SDK session, aliases hydrate display without demo fallback, account switches block writes, password reauthentication is isolated, wrong/current policy failures remain errors, and temporary sessions are closed. Mock provider only.');
})().catch(e=>{console.error(e);process.exitCode=1}).finally(()=>fs.rmSync(out,{force:true}));

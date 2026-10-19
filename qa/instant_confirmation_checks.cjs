const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const root=path.resolve(__dirname,'..'),out=path.join(root,'qa/.instant-confirmation.cjs');
let owner='owner-a',calls=0,resolve,reject;
const fixture={id:'QA',status:'unreviewed',frames:[{id:'photo-1',imageDataUrl:'data:image/jpeg;base64,TEST_ONLY'}],detections:[]};
global.__instant={owner:()=>owner,cached:()=>fixture,review:()=>{calls++;return new Promise((a,b)=>{resolve=a;reject=b})}};
(async()=>{
 await require(path.join(root,'node_modules/esbuild')).build({entryPoints:[path.join(root,'src/services/incidentConfirmation.ts')],bundle:true,platform:'node',format:'cjs',outfile:out,plugins:[{name:'isolated-transport',setup(b){b.onResolve({filter:/\/(auth|api)\.ts$/},args=>({path:args.path.includes('auth')?'auth':'api',namespace:'fake'}));b.onLoad({filter:/.*/,namespace:'fake'},args=>({contents:args.path==='auth'?'export const getCurrentAccountId=()=>globalThis.__instant.owner();':'export const getCachedIncident=()=>globalThis.__instant.cached();export const reviewIncident=(...args)=>globalThis.__instant.review(...args);',loader:'js'}));}}],logLevel:'silent'});
 const service=require(out),first=service.beginIncidentConfirmation('QA');
 assert.equal(calls,1);assert.equal(first.incident.status,'unreviewed');assert.equal(first.incident.frames[0].id,'photo-1');assert.equal(service.beginIncidentConfirmation('QA'),first);assert.equal(calls,1);
 let done=false;first.result.then(()=>done=true);await Promise.resolve();assert.equal(done,false);assert.equal(service.pendingIncidentConfirmation('QA').incident.frames.length,1);
 resolve({...fixture,status:'confirmed'});assert.equal((await first.result).status,'confirmed');service.finishIncidentConfirmation(first);assert.equal(service.pendingIncidentConfirmation('QA'),null);
 const failed=service.beginIncidentConfirmation('QA');reject(Error('Storage unavailable'));await assert.rejects(failed.result,/Storage unavailable/);assert.equal(failed.incident.frames.length,1);assert.equal(failed.incident.status,'unreviewed');service.finishIncidentConfirmation(failed);
 const switching=service.beginIncidentConfirmation('QA');owner='owner-b';assert.equal(service.pendingIncidentConfirmation('QA'),null);resolve({...fixture,status:'confirmed'});await assert.rejects(switching.result,/Account changed/);

 owner='owner-a';let releaseUpload,saveCalls=0;const image=new Blob(['isolated capture'],{type:'image/jpeg'});
 const capture={sample:{image,response:{detections:[]}},save:()=>{saveCalls++;return new Promise(r=>releaseUpload=r)}};
 const started=performance.now(),preview=service.beginCaptureConfirmation(capture);
 assert.ok(performance.now()-started<1000);assert.equal(preview.previewOnly,true);assert.ok(preview.incident.frames[0].imageDataUrl.startsWith('blob:'));assert.equal(preview.incident.status,'unreviewed');assert.equal(saveCalls,1);const callsBeforeUpload=calls;
 await Promise.resolve();assert.equal(calls,callsBeforeUpload);releaseUpload({...fixture,id:'persisted-camera'});await Promise.resolve();await Promise.resolve();assert.equal(calls,callsBeforeUpload+1);resolve({...fixture,id:'persisted-camera',status:'confirmed'});assert.equal((await preview.result).id,'persisted-camera');service.finishIncidentConfirmation(preview);
 owner=null;assert.throws(()=>service.beginIncidentConfirmation('QA'),/not ready/);

 console.log('PASS: saved photos available immediately while a deliberately stalled confirmation stays pending; duplicate submission blocked, real acknowledgement required, failure retains evidence, account switching discards task. Isolated transport.');
})().catch(e=>{console.error(e);process.exitCode=1}).finally(()=>fs.rmSync(out,{force:true}));

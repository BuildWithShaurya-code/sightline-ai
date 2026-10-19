// API-client contract: every setting reaches exactly one /api/v1 route.
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const root=path.resolve(__dirname,'..'),esbuild=require(path.join(root,'node_modules/esbuild'));
const cases=[['',''],['/api/v1',''],[' /api/v1/ ',''],['http://127.0.0.1:8000','http://127.0.0.1:8000'],['https://api.sightline.example/api/v1/','https://api.sightline.example'],['/backend/api/v1','/backend']];
(async()=>{
 for(let n=0;n<cases.length;n++){
  const [setting,base]=cases[n],out=path.join(root,`qa/.api-routing-${n}.cjs`),calls=[];
  try{
   await esbuild.build({entryPoints:[path.join(root,'src/services/api.ts')],outfile:out,bundle:true,platform:'node',format:'cjs',define:{'import.meta.env':JSON.stringify({VITE_API_URL:setting})},plugins:[{name:'isolated-auth',setup(b){b.onResolve({filter:/\/auth\.ts$/},()=>({path:'auth',namespace:'fixture'}));b.onLoad({filter:/.*/,namespace:'fixture'},()=>({contents:'export const getCurrentAccountId=()=>null;export const getAccessToken=async()=>"isolated-test-token";',loader:'js'}));}}],logLevel:'silent'});
   global.fetch=async(url,init)=>{
    calls.push([url,init]);
    assert.ok(!url.includes('/api/v1/api/v1/'));assert.equal(init.headers.Authorization,'Bearer isolated-test-token');
    let body=url.endsWith('/health/live')?{status:'live'}:url.endsWith('/health/ready')?{status:'ready',phase:4,components:{}}:{original_width:20,original_height:20,detections:[{classId:'mask',confidence:.85,box:[1,1,19,19]}]};
    return new Response(JSON.stringify(body),{headers:{'Content-Type':'application/json'}});
   };
   const api=require(out);assert.equal(api.getApiBaseUrl(),base);
   await api.checkHealthLive();await api.checkHealthReady();
   const result=await api.inferSingleImage(new Blob(['synthetic'],{type:'image/jpeg'}),['mask'],.25);
   assert.equal(result.detections[0].classId,'mask');assert.equal(calls[2][0],base+'/api/v1/inference/image');assert.equal(calls[2][1].method,'POST');assert.ok(calls[2][1].body instanceof FormData);assert.equal(calls[2][1].body.get('targets'),'mask');assert.equal(calls[2][1].body.get('confidence_threshold'),'0.25');
  }finally{fs.rmSync(out,{force:true});}
 }
 const timeoutFile=path.join(root,'qa/.api-timeout.cjs');
 try{
  await esbuild.build({entryPoints:[path.join(root,'src/services/api.ts')],outfile:timeoutFile,bundle:true,platform:'node',format:'cjs',define:{'import.meta.env':'{}'},plugins:[{name:'isolated-auth',setup(b){b.onResolve({filter:/\/auth\.ts$/},()=>({path:'auth',namespace:'fixture'}));b.onLoad({filter:/.*/,namespace:'fixture'},()=>({contents:'export const getCurrentAccountId=()=>null;export const getAccessToken=()=>globalThis.__pendingToken?new Promise(()=>{}):Promise.resolve(null);',loader:'js'}));}}],logLevel:'silent'});
  const api=require(timeoutFile);
  global.fetch=(_url,init)=>new Promise((resolve,reject)=>{const abort=()=>reject(new DOMException('Cancelled','AbortError'));if(init.signal.aborted)abort();else init.signal.addEventListener('abort',abort,{once:true});});
  await assert.rejects(api.checkHealthLive({timeoutMs:5}),error=>error instanceof api.TimeoutError&&error.errorCode==='REQUEST_TIMEOUT');
  const caller=new AbortController();const request=api.checkHealthLive({timeoutMs:1000,signal:caller.signal});caller.abort();
  await assert.rejects(request,error=>error.errorCode==='ABORTED');
  global.__pendingToken=true;
  await assert.rejects(api.checkHealthLive({timeoutMs:5}),error=>error.errorCode==='REQUEST_TIMEOUT');
  const pendingCaller=new AbortController();const pendingRequest=api.checkHealthLive({timeoutMs:1000,signal:pendingCaller.signal});pendingCaller.abort();
  await assert.rejects(pendingRequest,error=>error.errorCode==='ABORTED');global.__pendingToken=false;
 }finally{fs.rmSync(timeoutFile,{force:true});}
 console.log('PASS: timeout remains a timeout; explicit caller cancellation remains cancellation.');
 console.log('PASS: frontend health and camera inference use exactly one API prefix for six local/cloud URL configurations; multipart, bearer token and mask threshold are preserved. Isolated transport contract.');
})().catch(e=>{console.error(e);process.exitCode=1});

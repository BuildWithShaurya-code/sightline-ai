const assert=require('node:assert/strict'),path=require('node:path'),fs=require('node:fs');
const root=path.resolve(__dirname,'..'),out=path.join(root,'qa/.autosave.cjs');
require(path.join(root,'node_modules/esbuild')).buildSync({entryPoints:[path.join(root,'src/services/setupAutosave.ts')],bundle:true,platform:'node',format:'cjs',outfile:out,logLevel:'silent'});
const {createSetupAutosave}=require(out),tick=()=>new Promise(r=>setTimeout(r,20));
(async()=>{
 const writes=[],states=[];let fail=false,release,block=false;
 const saver=createSetupAutosave(async value=>{writes.push(value);if(block)await new Promise(r=>release=r);if(fail)throw Error('offline')},s=>states.push(s),5);
 saver.prime('stored');saver.schedule('stored');await tick();assert.deepEqual(writes,[]);assert.equal(states.at(-1).status,'saved');
 saver.schedule('first');saver.schedule('latest');await tick();assert.deepEqual(writes,['latest']);assert.equal(states.at(-1).status,'saved');
 saver.schedule('invalidated');saver.invalidate();await tick();assert.equal(writes.length,1);
 block=true;saver.schedule('in-flight');await tick();assert.equal(writes.at(-1),'in-flight');saver.schedule('newer');saver.schedule('newest');block=false;release();await tick();assert.deepEqual(writes,['latest','in-flight','newest']);assert.equal(states.at(-1).status,'saved');
 fail=true;assert.equal(await saver.flush('failed'),false);assert.equal(states.at(-1).status,'error');fail=false;assert.equal(await saver.flush('retry'),true);assert.equal(states.at(-1).status,'saved');
 block=true;const duplicateFirst=saver.flush('same-in-flight');await tick();const duplicateSecond=saver.flush('same-in-flight');block=false;release();assert.equal(await duplicateFirst,true);assert.equal(await duplicateSecond,true);assert.equal(writes.filter(v=>v==='same-in-flight').length,1);
 const count=writes.length;saver.schedule('discard-on-account-switch');saver.dispose();await tick();assert.equal(writes.length,count);
 let done;const observed=[];const old=createSetupAutosave(()=>new Promise(r=>done=r),s=>observed.push(s),0);old.schedule('old-owner');await tick();old.dispose();const before=observed.length;done();await tick();assert.equal(observed.length,before);
 console.log('PASS: unchanged data is not autosaved, edits debounce, writes serialize and keep the latest draft, invalid drafts cancel pending saves, failures are not acknowledged, retry succeeds, and disposal cancels queued work/stale success.');
})().catch(e=>{console.error(e);process.exitCode=1}).finally(()=>fs.rmSync(out,{force:true}));

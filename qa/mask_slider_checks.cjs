// Pure alert + pointer interaction tests; no real siren, notification or dismissal occurs.
const assert=require('node:assert/strict'),path=require('node:path'),fs=require('node:fs');
const root=path.resolve(__dirname,'..'),out=path.join(root,'qa/.mask-slider-check.cjs');
require(path.join(root,'node_modules/esbuild')).buildSync({stdin:{contents:`export * from './src/services/maskAlerts.ts';export * from './src/services/slideGesture.ts';`,resolveDir:root},bundle:true,platform:'node',format:'cjs',outfile:out,logLevel:'silent'});
try{
 const {MaskAlertGate,MASK_ALERT_MIN_CONFIDENCE,maskAlertConfidence,SlideGesture}=require(out);
 const mask=confidence=>({classId:'mask',confidence});assert.equal(MASK_ALERT_MIN_CONFIDENCE,.6);
 for(const value of [0,.25,.59,.599999,NaN,Infinity,1.01]){
  assert.equal(maskAlertConfidence([mask(value)]),null);assert.equal(new MaskAlertGate().observeDetections([mask(value)],0),null);
 }
 assert.equal(maskAlertConfidence([mask(.6)]),.6);assert.equal(maskAlertConfidence([mask(.61),mask(.91)]),.91);
 assert.equal(new MaskAlertGate().observeDetections([{classId:'person',confidence:.99},{classId:'knife',confidence:.99}],0),null);
 const gate=new MaskAlertGate();assert.equal(gate.observeDetections([mask(.6)],0),.6);assert.equal(gate.observeDetections([mask(.9)],500),null);
 for(let i=0;i<3;i++)assert.equal(gate.observeDetections([mask(.59)],1000+i),null);
 assert.equal(gate.observeDetections([mask(.95)],29999),null);assert.equal(gate.observeDetections([mask(.95)],30000),.95);
 const live=new MaskAlertGate();assert.equal(live.observe({response:{detections:[mask(.59)]}},0),null);assert.equal(live.observe({response:{detections:[mask(.6)]}},1),.6);
 const g=new SlideGesture();assert.equal(g.start(1,30,300),true);assert.equal(g.finish(1,30),'tap');assert.equal(g.finish(1,30),null);
 g.start(1,30,300);g.move(1,150);assert.equal(g.finish(1,150),'cancel');assert.equal(g.progress,0);
 g.start(1,30,300);g.move(1,290);assert.equal(g.finish(1,290),'complete');
 g.start(1,30,300);g.move(1,200);g.move(1,30);assert.equal(g.finish(1,30),'cancel'); // a drag returning to start is not a tap
 g.start(1,30,300);assert.equal(g.start(2,30,300),false);assert.equal(g.finish(2,400),null);g.cancel();assert.equal(g.finish(1,400),null);
 g.start(1,30,300);assert.equal(g.finish(1,285),'complete'); // exact 85% boundary
 g.start(1,30,300);assert.equal(g.finish(1,284),'cancel');
 assert.equal(g.step(.25),false);assert.equal(g.step(.25),false);assert.equal(g.step(.25),false);assert.equal(g.step(.25),true);g.cancel();assert.equal(g.progress,0);
 g.start(1,0,120);g.move(1,500);assert.equal(g.progress,1);assert.equal(g.finish(1,500),'complete');
 const studio=fs.readFileSync(path.join(root,'src/components/screens/DetectionStudioScreen.tsx'),'utf8');
 assert.ok(!studio.includes("'Saving evidence…'"));assert.ok(!studio.includes('confirmingThreat || autoEvidence.saving'));assert.ok(studio.includes('incidentReady={Boolean(savedIncidentId)||autoEvidence.canConfirm}'));
 console.log('PASS: live/completed mask alert thresholds (below/exact/above 60%), invalid values, non-mask exclusion, episode/cooldown behavior; taps, partial/full/85%-boundary drags, return drags, cancellation, duplicate/wrong-pointer events and keyboard progression.');
}finally{fs.rmSync(out,{force:true})}

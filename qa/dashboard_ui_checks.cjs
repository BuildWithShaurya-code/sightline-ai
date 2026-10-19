// Rendering checks for truthful status, persistent setup entry and summary clarity.
const path=require('node:path'),assert=require('node:assert/strict'),fs=require('node:fs');
const root=path.resolve(__dirname,'..'),out=path.join(root,'qa/.dashboard-cards.cjs');
require(path.join(root,'node_modules/esbuild')).buildSync({entryPoints:[path.join(root,'src/components/dashboard/DashboardCards.tsx')],bundle:true,platform:'node',format:'cjs',outfile:out,external:['react'],logLevel:'silent'});
try{
 const React=require(path.join(root,'node_modules/react')),render=require(path.join(root,'node_modules/react-dom/server')).renderToStaticMarkup;
 const {DashboardSecuritySetup,SystemStatusCard,LatestIncidentCard}=require(out);
 for(const complete of [true,false])for(const later of [true,false]){
  const html=render(React.createElement(DashboardSecuritySetup,{complete,later,loading:false,error:'',onLater(){},onOpen(){}}));
  assert.ok(html.includes('Security contacts &amp; location'));assert.ok(html.includes('type="button"'));
  assert.equal(html.includes('Set up now'),!complete&&!later);
 }
 const offline=render(React.createElement(SystemStatusCard,{ready:false,checking:false,checkedAt:null}));assert.ok(offline.includes('Offline'));assert.ok(!offline.includes('Ready to analyze'));
 const checking=render(React.createElement(SystemStatusCard,{ready:false,checking:true,checkedAt:null}));assert.ok(checking.includes('Checking model'));assert.ok(!checking.includes('Reconnect before'));
 const ready=render(React.createElement(SystemStatusCard,{ready:true,checking:false,checkedAt:new Date('2026-10-19T05:00:00Z')}));assert.ok(ready.includes('Ready to analyze'));assert.ok(ready.includes('Checked'));
 const html=render(React.createElement(LatestIncidentCard,{incident:{id:'QA',createdAt:'2026-10-19T05:00:00Z',status:'unreviewed',frames:[],title:'Mask detected — automatic camera evidence',channel:'LIVE CAMERA',detections:[{classId:'mask',confidence:.81},{classId:'mask',confidence:.91},{classId:'person',confidence:.8}]},onOpen(){}}));
 assert.ok(html.includes('Mask detected'));assert.ok(!html.includes('automatic camera evidence'));assert.ok(!html.includes('target(s)'));assert.ok(html.includes('91%'));assert.ok(!html.includes('81%'));assert.ok(html.includes('Review incident'));
 console.log('PASS: dashboard setup remains available after saved setup or Later, health states stay truthful, latest alert titles are short and repeated class predictions collapse to highest confidence. Rendering checks only.');
}finally{fs.rmSync(out,{force:true})}

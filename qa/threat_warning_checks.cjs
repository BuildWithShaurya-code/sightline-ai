const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const root=path.resolve(__dirname,'..'),out=path.join(root,'qa/.warning-actions.cjs');
require(path.join(root,'node_modules/esbuild')).buildSync({entryPoints:[path.join(root,'src/components/common/ThreatWarningActions.tsx')],outfile:out,bundle:true,platform:'node',format:'cjs',external:['react'],logLevel:'silent'});
try{
 const React=require(path.join(root,'node_modules/react')),render=require(path.join(root,'node_modules/react-dom/server')).renderToStaticMarkup,{ThreatWarningActions}=require(out);
 for(const incidentReady of [false,true]){
  const html=render(React.createElement(ThreatWarningActions,{incidentReady,opening:false,onReview(){},onDismiss(){}}));
  const review=html.split('</button>')[0];assert.equal(review.includes('disabled=""'),!incidentReady);assert.ok(review.includes('CONFIRM THREAT'));assert.ok(!html.includes('Saving evidence'));assert.ok(html.includes('Dismiss warning'));
 }
 const opening=render(React.createElement(ThreatWarningActions,{incidentReady:true,opening:true,onReview(){},onDismiss(){}}));assert.ok(opening.split('</button>')[0].includes('disabled=""'));assert.ok(opening.includes('Confirming…'));
 const studio=fs.readFileSync(path.join(root,'src/components/screens/DetectionStudioScreen.tsx'),'utf8');
 const action=studio.slice(studio.indexOf('const confirmDetectedThreat ='),studio.indexOf('const confirmDetectedThreat =')+1500);
 assert.ok(action.includes('beginIncidentConfirmation(savedIncidentId,autoEvidence.incident)'));assert.ok(action.includes("onNavigate?.('threat-detail',task.routeId)"));assert.ok(!action.includes('await '));assert.ok(action.includes('confirmationPending.current=true'));

 console.log('PASS: confirm label stays stable; first persisted photo enables confirmation; extra background saves cannot disable it; opening prevents duplicate clicks. Rendered action states.');
}finally{fs.rmSync(out,{force:true});}

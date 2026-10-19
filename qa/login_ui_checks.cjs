/* Server rendering checks only; browser/password-manager autofill behavior is not simulated. */
const path=require('node:path'),assert=require('node:assert/strict');
const root=path.resolve(__dirname,'..');
const esbuild=require(path.join(root,'node_modules/esbuild'));
const file=path.join(root,'qa/.login-render-check.cjs');
esbuild.buildSync({entryPoints:[path.join(root,'src/components/screens/OperatorLoginScreen.tsx')],bundle:true,platform:'node',format:'cjs',outfile:file,external:['react','@supabase/supabase-js'],define:{'import.meta.env':'{}'},logLevel:'silent'});
try {
 const React=require(path.join(root,'node_modules/react')),server=require(path.join(root,'node_modules/react-dom/server'));
 const {OperatorLoginScreen}=require(file);const html=server.renderToStaticMarkup(React.createElement(OperatorLoginScreen));
 assert.ok(!html.includes('Quick Demo Access'));assert.ok(!html.includes('tactical2026'));
 assert.equal((html.match(/value=""/g)||[]).length,2);assert.equal((html.match(/class="login-input/g)||[]).length,2);
 assert.ok(html.includes('autoComplete="off"'));assert.ok(html.includes('Slide to sign in'));assert.ok(html.includes('Username'));assert.ok(html.includes('Enter your password'));assert.ok(!html.includes('Passcode Protocol'));assert.ok(!html.includes('ACTIVE NEURAL GUARD'));assert.ok(html.includes('aria-valuetext="0%'));
 assert.equal((html.match(/readOnly=""/g)||[]).length,2);
 assert.ok(html.includes('Create an account'));assert.ok(html.indexOf('Account access')<html.indexOf('Username'));assert.ok(html.includes('New users can create an account above.'));
 const signup=server.renderToStaticMarkup(React.createElement(OperatorLoginScreen,{initialMode:'signup'}));
 for(const label of ['Create your account','Choose your username','Confirm password','Create account'])assert.ok(signup.includes(label));
 assert.equal((signup.match(/class="login-input/g)||[]).length,3);
 assert.ok(!signup.includes('Slide to sign in'));assert.ok(!signup.includes('Email address'));assert.ok(!signup.includes('signup-email')); 
 assert.ok(!signup.includes('value="larpers"')); 
 console.log('PASS: login renders blank navy-styled fields, no demo access button, autocomplete disabled, focus-to-edit fields and accessible sign-in slider. Server rendering only; browser autofill is not certified.');
} finally {require('node:fs').unlinkSync(file);}

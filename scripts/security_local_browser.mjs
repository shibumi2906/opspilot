import {lookup} from 'node:dns/promises';
import assert from 'node:assert/strict';
import { readFileSync, writeFileSync } from 'node:fs';
import { X509Certificate, createHash, createHmac, randomUUID } from 'node:crypto';
import { createRequire } from 'node:module';
const require=createRequire('/app/web/package.json');
const {chromium}=require('playwright');
const lab='/lab/';
const credentials=JSON.parse(readFileSync(lab+'credentials.json'));
const secrets=JSON.parse(readFileSync(lab+'otp-fixtures.json'));
const origin='https://app.opspilot.localhost:8443';
const issuer='https://idp.opspilot.localhost:8543';
const pins=['app.opspilot.localhost','idp.opspilot.localhost'].map(n=>createHash('sha256').update(new X509Certificate(readFileSync(lab+n+'.crt')).publicKey.export({type:'spki',format:'der'})).digest('base64')).join(',');
// Only two generated leaf public keys are accepted by Chromium; Node HTTPS uses the lab CA.
const appIP=(await lookup('web')).address,idpIP=(await lookup('oidc')).address;
const browser=await chromium.launch({args:['--ignore-certificate-errors-spki-list='+pins,'--host-resolver-rules=MAP app.opspilot.localhost '+appIP+', MAP idp.opspilot.localhost '+idpIP]});
const context=await browser.newContext();
const page=await context.newPage(); page.setDefaultTimeout(15000);
page.on('response',r=>{if(r.url().startsWith(origin+'/auth/callback'))console.log('callback status',r.status());});
const checks=[];
async function chooseTenant(p) {
 const selector=p.getByLabel('Tenant',{exact:true});
 const target='aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa';
 await selector.waitFor();
 if(await selector.inputValue() !== target) {
   await Promise.all([
     p.waitForEvent('framenavigated',frame=>frame===p.mainFrame()),
     selector.selectOption(target),
   ]);
 }
 await p.waitForLoadState('networkidle');
 await p.getByLabel('Tenant',{exact:true}).waitFor();
 assert.equal(await p.getByLabel('Tenant',{exact:true}).inputValue(),target);
}
function otp(name){const b=Buffer.alloc(8);b.writeBigUInt64BE(BigInt(Math.floor(Date.now()/30000)));const h=createHmac('sha1',secrets[name]).update(b).digest();const i=h[19]&15;return String((h.readUInt32BE(i)&0x7fffffff)%1000000).padStart(6,'0');}
try {
 await page.goto(origin);
 await page.getByRole('link',{name:'Sign in',exact:true}).click();
 await page.locator('#username').fill('operator');
 await page.locator('#password').fill(credentials.user);
 await page.locator('#kc-login').click();
 await page.locator('#otp').waitFor();
 assert(!(await context.cookies(origin)).some(c=>c.name==='__Host-opspilot_session'));
 checks.push('password alone cannot establish application session');
 await page.locator('#otp').fill(String((Number(otp('operator'))+1)%1000000).padStart(6,'0'));
 await page.locator('#kc-login').click();
 await page.locator('#otp').waitFor();
 assert(page.url().startsWith(issuer));
 checks.push('invalid OTP denied');
 await page.locator('#otp').fill(otp('operator'));
 await page.locator('#kc-login').click();
 await page.waitForURL(origin+'/',{timeout:30000});
 await page.getByLabel('Tenant',{exact:true}).waitFor();
 const cookie=(await context.cookies(origin)).find(c=>c.name==='__Host-opspilot_session');
 assert(cookie?.secure && cookie.httpOnly && cookie.path==='/' && cookie.domain==='app.opspilot.localhost');
 checks.push('password + one-time TOTP creates Secure HttpOnly host cookie');
 let me=await page.evaluate(async()=>{const r=await fetch('/auth/me');return {status:r.status,body:await r.json()};});
 assert.equal(me.status,200);
 checks.push('provider userinfo validates live MFA session over trusted TLS');
 await chooseTenant(page);
 me=await page.evaluate(async()=>{const r=await fetch('/auth/me');return {status:r.status,body:await r.json()};});
 const sessions=await page.evaluate(async()=>{const r=await fetch('/auth/sessions');return {status:r.status,body:await r.json()};});
 assert.equal(sessions.status,200);assert(sessions.body.items.length>=1);
 assert(!JSON.stringify(sessions).includes('ciphertext'));
 checks.push('own session inventory exposes metadata only');
 const expiryPage=await context.newPage();
 await expiryPage.route('**/auth/me',route=>route.fulfill({json:{...me.body,session_expires_at:new Date(Date.now()+3000).toISOString(),session_idle_expires_at:new Date(Date.now()+3000).toISOString()}}));
 await expiryPage.goto(origin); await expiryPage.getByRole('button',{name:'Sign out',exact:true}).waitFor();
 await context.setOffline(true);
 await expiryPage.getByRole('link',{name:'Sign in',exact:true}).waitFor({timeout:7000});
 assert.equal(await expiryPage.locator('.identity-bar').count(),0);
 await context.setOffline(false); await expiryPage.close();
 checks.push('offline private UI clears at its server deadline (short deadline response fixture)');
 const logoutPage=await context.newPage();await logoutPage.goto(origin);
 await logoutPage.getByRole('button',{name:'Sign out',exact:true}).waitFor();
 await context.setOffline(true);await logoutPage.getByRole('button',{name:'Sign out',exact:true}).click();
 await logoutPage.getByRole('link',{name:'Sign in',exact:true}).waitFor({timeout:1500});
 assert.equal(await logoutPage.locator('.identity-bar').count(),0);
 await context.setOffline(false);await logoutPage.close();
 checks.push('offline sign-out clears private DOM immediately without claiming server revocation');
 const created=await page.evaluate(async({csrf,id})=>{const r=await fetch('/api/v2/runs',{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':csrf},body:JSON.stringify({request:'Investigate GreenShop checkout incident',client_request_id:id})});return {status:r.status,body:await r.json()};},{csrf:me.body.csrf_token,id:randomUUID()});
 assert([200,202].includes(created.status), 'run creation status '+created.status);
 checks.push('authorized run accepted in hardened profile');
 async function savedSnapshot(p) {
   for(let attempt=0;attempt<180;attempt++) {
     const r=await p.evaluate(async path=>{const response=await fetch(path);return {status:response.status,body:await response.json()};},created.body.snapshot_url);
     assert.equal(r.status,200);
     if(!['queued','running'].includes(r.body.status)) return r.body;
     await p.waitForTimeout(250);
   }
   throw Error('Hardened worker did not reach a saved result');
 }
 const pending=await savedSnapshot(page);assert.equal(pending.status,'waiting_for_approval');
 const forbidden=await page.evaluate(async({path,csrf,action})=>(await fetch(path+'/decision',{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':csrf},body:JSON.stringify({action_id:action,decision:'approve',expected_version:1})})).status,{path:created.body.snapshot_url,csrf:me.body.csrf_token,action:pending.action.action_id});
 assert.equal(forbidden,403);
 const approvalContext=await browser.newContext();const approvalPage=await approvalContext.newPage();approvalPage.setDefaultTimeout(15000);
 try {
   await approvalPage.goto(origin);await approvalPage.getByRole('link',{name:'Sign in',exact:true}).click();
   await approvalPage.locator('#username').fill('approver');await approvalPage.locator('#password').fill(credentials.user);await approvalPage.locator('#kc-login').click();
   await approvalPage.locator('#otp').fill(otp('approver'));await approvalPage.locator('#kc-login').click();
   await approvalPage.waitForURL(origin+'/');await chooseTenant(approvalPage);
   const approver=await approvalPage.evaluate(async()=> (await fetch('/auth/me')).json());
   const accepted=await approvalPage.evaluate(async({path,csrf,action})=>(await fetch(path+'/decision',{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':csrf},body:JSON.stringify({action_id:action,decision:'approve',expected_version:1})})).status,{path:created.body.snapshot_url,csrf:approver.csrf_token,action:pending.action.action_id});
   assert.equal(accepted,202);
   const completed=await savedSnapshot(approvalPage);assert.equal(completed.status,'completed');assert.equal(completed.outcome,'actions_verified');
   checks.push('operator cannot approve; separate fresh-MFA approver completes signed TLS MCP action with verified outcome');
 } finally {await approvalContext.close();}

 // Direct IdP administrative disable must invalidate an existing BFF session.
 const tokenResponse=await fetch(issuer+'/realms/master/protocol/openid-connect/token',{method:'POST',headers:{'Content-Type':'application/x-www-form-urlencoded'},body:new URLSearchParams({client_id:'admin-cli',grant_type:'password',username:'security-admin',password:credentials.admin})});
 assert.equal(tokenResponse.status,200);const adminToken=(await tokenResponse.json()).access_token;
 const userId='00000000-0000-0000-0000-000000002711';
 const disable=await fetch(issuer+'/admin/realms/opspilot/users/'+userId,{method:'PUT',headers:{Authorization:'Bearer '+adminToken,'Content-Type':'application/json'},body:JSON.stringify({enabled:false})});
 assert.equal(disable.status,204);
 const disabled=await page.evaluate(async()=> (await fetch('/auth/me')).status);
 const enable=await fetch(issuer+'/admin/realms/opspilot/users/'+userId,{method:'PUT',headers:{Authorization:'Bearer '+adminToken,'Content-Type':'application/json'},body:JSON.stringify({enabled:true})});
 assert.equal(enable.status,204);
 assert.equal(disabled,401);
 checks.push('IdP account disable revokes existing BFF session on next request');
 const denied=await page.evaluate(async()=> (await fetch('/auth/me')).status);
 assert.equal(denied,401);
 checks.push('re-enabling IdP account cannot resurrect revoked BFF session');
 writeFileSync('/reports/browser.json',JSON.stringify({passed:true,checks,browserCertificatePolicy:'two pinned generated leaf SPKIs; no global ignoreHTTPS; Node validates CA',synthetic:true},null,2));
 console.log(JSON.stringify({passed:true,checks}));
} catch(e){console.error('Security browser check failed:',e.message);process.exitCode=1;}
finally{await browser.close();}

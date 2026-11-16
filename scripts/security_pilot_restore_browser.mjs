// Browser acceptance after whole-pilot restore. Only synthetic local writes are allowed.
import assert from 'node:assert/strict';
import {readFileSync,writeFileSync} from 'node:fs';
import {lookup} from 'node:dns/promises';
import {X509Certificate,createHash,createHmac} from 'node:crypto';
import {createRequire} from 'node:module';
const require=createRequire('/app/web/package.json'),{chromium}=require('playwright');
const credentials=JSON.parse(readFileSync('/lab/credentials.json'));
const secrets=JSON.parse(readFileSync('/lab/otp-fixtures.json'));
const fixture=JSON.parse(readFileSync('/lab/recovery-fixture.json'));
const origin='https://app.opspilot.localhost:8443',issuer='https://idp.opspilot.localhost:8543';
const pins=['app.opspilot.localhost','idp.opspilot.localhost'].map(n=>createHash('sha256').update(new X509Certificate(readFileSync('/lab/'+n+'.crt')).publicKey.export({type:'spki',format:'der'})).digest('base64')).join(',');
const appIP=(await lookup('web')).address,idpIP=(await lookup('oidc')).address;
const browser=await chromium.launch({args:['--ignore-certificate-errors-spki-list='+pins,'--host-resolver-rules=MAP app.opspilot.localhost '+appIP+', MAP idp.opspilot.localhost '+idpIP]});
let stage='login';
function otp(key){const b=Buffer.alloc(8);b.writeBigUInt64BE(BigInt(Math.floor(Date.now()/30000)));const h=createHmac('sha1',key).update(b).digest(),i=h[19]&15;return String((h.readUInt32BE(i)&0x7fffffff)%1000000).padStart(6,'0');}
async function login(role){
  const context=await browser.newContext(),page=await context.newPage();page.setDefaultTimeout(20000);
  await page.goto(origin);await page.getByRole('link',{name:'Sign in',exact:true}).click();
  await page.locator('#username').fill(role);await page.locator('#password').fill(credentials.user);
  await page.locator('#kc-login').click();await page.locator('#otp').fill(otp(secrets[role]));
  await page.locator('#kc-login').click();await page.waitForURL(origin+'/');
  const selector=page.getByLabel('Tenant',{exact:true});await selector.waitFor();
  if(await selector.inputValue()!==fixture.tenant){await selector.selectOption(fixture.tenant);await page.waitForLoadState('networkidle');}
  assert.equal(await page.getByLabel('Tenant',{exact:true}).inputValue(),fixture.tenant);
  return page;
}
async function get(page,path){return page.evaluate(async p=>{const r=await fetch(p);return {status:r.status,body:await r.json()};},path);}
async function decide(page,run,action){
  const me=await get(page,'/auth/me');assert.equal(me.status,200);
  return page.evaluate(async({run,action,csrf})=>(await fetch('/api/v2/runs/'+run+'/decision',{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':csrf},body:JSON.stringify({action_id:action.action_id,expected_version:action.expected_version,decision:'approve'})})).status,{run,action,csrf:me.body.csrf_token});
}
try{
  const operator=await login('operator');
  stage='preserved checkpoints';
  const pending=await get(operator,'/api/v2/runs/'+fixture.pending);assert.equal(pending.status,200);assert.equal(pending.body.status,'waiting_for_approval');
  const committed=await get(operator,'/api/v2/runs/'+fixture.committed);assert.equal(committed.status,200);assert.equal(committed.body.status,'completed');assert.equal(committed.body.outcome,'actions_verified');
  assert.equal(await decide(operator,fixture.pending,pending.body.action),403);
  stage='restored approval';
  const approver=await login('approver');
  assert.equal(await decide(approver,fixture.pending,pending.body.action),202);
  let final;
  for(let attempt=0;attempt<180;attempt++){
    final=await get(operator,'/api/v2/runs/'+fixture.pending);assert.equal(final.status,200);
    if(final.body.status==='completed')break;
    assert(!['failed','needs_attention','cancelled'].includes(final.body.status));
    await new Promise(resolve=>setTimeout(resolve,250));
  }
  assert.equal(final.body.status,'completed');assert.equal(final.body.outcome,'actions_verified');
  stage='committed replay';
  const action=(committed.body.actions??[]).find(a=>a.tool_name==='create_ticket')??committed.body.action;assert(action);
  const replay=await decide(approver,fixture.committed,action);assert([200,202,409,410].includes(replay));
  stage='restored administrator MFA';
  const key=Buffer.from(JSON.parse(readFileSync('/lab/admin-mfa/credential.json')).raw_secret_base64,'base64');
  const params={client_id:'admin-cli',grant_type:'password',username:'security-admin',password:credentials.admin};
  const token=extra=>fetch(issuer+'/realms/master/protocol/openid-connect/token',{method:'POST',signal:AbortSignal.timeout(15000),headers:{'Content-Type':'application/x-www-form-urlencoded'},body:new URLSearchParams({...params,...extra})});
  assert([400,401].includes((await token({})).status));
  const admitted=await token({totp:otp(key)});assert.equal(admitted.status,200);
  const bearer=(await admitted.json()).access_token;
  assert.equal((await fetch(issuer+'/admin/realms/master',{signal:AbortSignal.timeout(15000),headers:{Authorization:'Bearer '+bearer}})).status,200);
  writeFileSync('/reports/restored-browser.json',JSON.stringify({passed:true,restored_user_mfa:true,pending_interrupt_preserved:true,pending_approval_completed:true,operator_approval_denied:true,committed_replay_status:replay,restored_master_admin_mfa:true,synthetic:true},null,2),{flag:'wx'});
  console.log(JSON.stringify({passed:true,scope:'restored TLS browser login, pending approval, committed replay and master administrator MFA'}));
}catch{console.error('Restored pilot browser failed at '+stage+'; private state preserved');process.exitCode=1;}
finally{await browser.close();}

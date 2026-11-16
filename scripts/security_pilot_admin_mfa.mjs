// Enroll and verify actual master-realm administrator MFA in an isolated local pilot.
import assert from 'node:assert/strict';
import {lookup} from 'node:dns/promises';
import {readFileSync, writeFileSync, existsSync, copyFileSync, constants} from 'node:fs';
import {X509Certificate, createHash, createHmac} from 'node:crypto';
import {createRequire} from 'node:module';
const require=createRequire('/app/web/package.json');
const {chromium}=require('playwright');
const lab='/lab/', state='/admin-state/credential.json';
const issuer='https://idp.opspilot.localhost:8543';
const credentials=JSON.parse(readFileSync(lab+'credentials.json'));
const fetch=(url,options={})=>globalThis.fetch(url,{signal:AbortSignal.timeout(15000),...options});
const resume=process.argv.includes('--resume-incomplete');
assert(!existsSync('/admin-state/verified.json'),'Verified administrator MFA must not be re-enrolled');
assert(resume===existsSync(state),'Existing administrator MFA state requires explicit inspection');
let stage='bootstrap',browser;
let lastCounter=-1;
function otp(key) {
  const b=Buffer.alloc(8);b.writeBigUInt64BE(BigInt(Math.floor(Date.now()/30000)));
  const h=createHmac('sha1',key).update(b).digest(),i=h[19]&15;
  return String((h.readUInt32BE(i)&0x7fffffff)%1000000).padStart(6,'0');
}
async function freshOtp(key) {
  while(Math.floor(Date.now()/30000)<=lastCounter) await new Promise(r=>setTimeout(r,250));
  lastCounter=Math.floor(Date.now()/30000);return otp(key);
}
async function token(extra={}) {
  return fetch(issuer+'/realms/master/protocol/openid-connect/token',{
    method:'POST',headers:{'Content-Type':'application/x-www-form-urlencoded'},
    body:new URLSearchParams({client_id:'admin-cli',grant_type:'password',
      username:'security-admin',password:credentials.admin,...extra}),
  });
}
try {
 if(!resume) {
  const bootstrap=await token();assert.equal(bootstrap.status,200);
  const bearer=(await bootstrap.json()).access_token;
  const headers={Authorization:'Bearer '+bearer,'Content-Type':'application/json'};
  const users=await fetch(issuer+'/admin/realms/master/users?username=security-admin&exact=true',{headers});
  assert.equal(users.status,200);const matches=await users.json();assert.equal(matches.length,1);
  const userURL=issuer+'/admin/realms/master/users/'+matches[0].id;
  const before=await fetch(userURL+'/credentials',{headers});assert.equal(before.status,200);
  assert(!(await before.json()).some(c=>c.type==='otp'),'Existing OTP must not be replaced');
  assert.equal((await fetch(userURL,{method:'PUT',headers,body:JSON.stringify({requiredActions:['CONFIGURE_TOTP']})})).status,204);
 }
  stage='browser enrollment';
  const pin=createHash('sha256').update(new X509Certificate(readFileSync(lab+'idp.opspilot.localhost.crt')).publicKey.export({type:'spki',format:'der'})).digest('base64');
  const ip=(await lookup('oidc')).address;
  browser=await chromium.launch({args:['--ignore-certificate-errors-spki-list='+pin,'--host-resolver-rules=MAP idp.opspilot.localhost '+ip]});
  const enrollment=await browser.newContext(),page=await enrollment.newPage();page.setDefaultTimeout(20000);
  await page.goto(issuer+'/admin/master/console/');
  await page.locator('#username').fill('security-admin');
  await page.locator('#password').fill(credentials.admin);await page.locator('#kc-login').click();
  await page.locator('#totpSecret').waitFor({state:'attached'});
  // Keycloak's hidden totpSecret is raw text; only its displayed QR/manual key is Base32.
  // https://github.com/keycloak/keycloak/blob/main/services/src/main/java/org/keycloak/utils/TotpUtils.java
  const key=Buffer.from(await page.locator('#totpSecret').inputValue(),'utf8');
  // Persist recovery state before submitting enrollment; never print it or overwrite it.
  if(resume)copyFileSync(state,'/admin-state/incomplete-attempt-1.json',constants.COPYFILE_EXCL);
  writeFileSync(state,JSON.stringify({raw_secret_base64:key.toString('base64'),phase:'enrollment submitted'}),{flag:resume?'w':'wx',mode:0o600});
  const label=page.locator('#userLabel');if(await label.count())await label.fill('OpsPilot local pilot administrator');
  stage='OTP registration submit';
  await page.locator('#totp').fill(await freshOtp(key));
  await page.locator('#saveTOTPBtn, #saveTOTP, input[type="submit"], button[type="submit"]').first().click();
  stage='OTP registration redirect';
  await page.waitForURL(issuer+'/admin/master/console/**',{timeout:30000});
  await enrollment.close();
  stage='password-only denial';
  assert([400,401].includes((await token()).status));
  stage='administrator OTP challenge';
  const context=await browser.newContext(),login=await context.newPage();login.setDefaultTimeout(20000);
  await login.goto(issuer+'/admin/master/console/');
  await login.locator('#username').fill('security-admin');
  await login.locator('#password').fill(credentials.admin);await login.locator('#kc-login').click();
  await login.locator('#otp').waitFor();
  await login.locator('#otp').fill(String((Number(otp(key))+1)%1000000).padStart(6,'0'));
  await login.locator('#kc-login').click();await login.locator('#otp').waitFor();
  assert(!login.url().includes('/admin/master/console/'));
  await login.locator('#otp').fill(await freshOtp(key));await login.locator('#kc-login').click();
  await login.waitForURL(issuer+'/admin/master/console/**',{timeout:30000});
  stage='privileged MFA token';
  const authenticated=await token({totp:await freshOtp(key)});assert.equal(authenticated.status,200);
  const access=(await authenticated.json()).access_token;
  const adminHeaders={Authorization:'Bearer '+access,'Content-Type':'application/json'};
  assert.equal((await fetch(issuer+'/admin/realms/master',{headers:adminHeaders})).status,200);
  // Invalidate pre-enrollment sessions and prove no password-only token can be minted.
  const users=await (await fetch(issuer+'/admin/realms/master/users?username=security-admin&exact=true',{headers:adminHeaders})).json();
  assert.equal(users.length,1);
  assert.equal((await fetch(issuer+'/admin/realms/master/users/'+users[0].id+'/logout',{method:'POST',headers:adminHeaders})).status,204);
  assert([400,401].includes((await token()).status));
  writeFileSync('/admin-state/verified.json',JSON.stringify({passed:true,realm:'master',administrator:'local pilot bootstrap identity',browser_password_alone_denied:true,invalid_otp_denied:true,browser_mfa_login:true,password_grant_without_otp_denied:true,privileged_mfa_token_verified:true,pre_enrollment_sessions_revoked:true,recovery:'Private OTP recovery state retained separately from public evidence; host encryption remains independently required'},null,2),{flag:'wx'});
  writeFileSync('/reports/admin-mfa.json',readFileSync('/admin-state/verified.json'),{flag:'wx'});
  console.log(JSON.stringify({passed:true,checks:7,scope:'actual local pilot master-realm administrator MFA'}));
} catch {
  console.error('Administrator MFA probe failed at '+stage+'; private enrollment state preserved');process.exitCode=1;
} finally {if(browser)await browser.close();}

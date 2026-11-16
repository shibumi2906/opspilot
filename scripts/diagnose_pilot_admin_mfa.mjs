// Read-only diagnosis: no OTP reset or re-enrollment, no private values in output.
import {readFileSync} from 'node:fs';
import {lookup} from 'node:dns/promises';
import {createHmac,createHash,X509Certificate} from 'node:crypto';
import {createRequire} from 'node:module';
const require=createRequire('/app/web/package.json'),{chromium}=require('playwright');
const issuer='https://idp.opspilot.localhost:8543';
const password=JSON.parse(readFileSync('/lab/credentials.json')).admin;
const key=Buffer.from(JSON.parse(readFileSync('/lab/admin-mfa/credential.json')).raw_secret_base64,'base64');
const b=Buffer.alloc(8);b.writeBigUInt64BE(BigInt(Math.floor(Date.now()/30000)));
const h=createHmac('sha1',key).update(b).digest(),i=h[19]&15;
const otp=String((h.readUInt32BE(i)&0x7fffffff)%1000000).padStart(6,'0');
const response=await fetch(issuer+'/realms/master/protocol/openid-connect/token',{
  method:'POST',signal:AbortSignal.timeout(10000),headers:{'Content-Type':'application/x-www-form-urlencoded'},
  body:new URLSearchParams({client_id:'admin-cli',grant_type:'password',username:'security-admin',password,totp:otp}),
});
const result={token_status:response.status};
if(response.status===200){
  const headers={Authorization:'Bearer '+(await response.json()).access_token};
  const users=await (await fetch(issuer+'/admin/realms/master/users?username=security-admin&exact=true',{headers})).json();
  const credentials=await (await fetch(issuer+'/admin/realms/master/users/'+users[0].id+'/credentials',{headers})).json();
  result.credential_types=credentials.map(c=>c.type);result.required_actions=users[0].requiredActions;
}
const pin=createHash('sha256').update(new X509Certificate(readFileSync('/lab/idp.opspilot.localhost.crt')).publicKey.export({type:'spki',format:'der'})).digest('base64');
const ip=(await lookup('oidc')).address;
const browser=await chromium.launch({args:['--ignore-certificate-errors-spki-list='+pin,'--host-resolver-rules=MAP idp.opspilot.localhost '+ip]});
try{
  const page=await browser.newPage();page.setDefaultTimeout(15000);
  await page.goto(issuer+'/admin/master/console/');
  await page.locator('#username').fill('security-admin');await page.locator('#password').fill(password);
  await page.locator('#kc-login').click();await page.waitForLoadState('networkidle');
  result.heading=await page.locator('h1,h2').allTextContents();
  result.form_controls=await page.locator('input,button').evaluateAll(nodes=>nodes.map(n=>({tag:n.tagName,id:n.id,name:n.name,type:n.type})));
  result.path=new URL(page.url()).pathname;
  console.log(JSON.stringify(result));
}finally{await browser.close();}

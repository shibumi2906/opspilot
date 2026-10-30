// Local Full only; real OIDC + scripted provider, no paid/vendor calls or SQL setup.
import assert from 'node:assert/strict';
import {readFileSync,writeFileSync} from 'node:fs';
import {chromium} from '../web/node_modules/playwright/index.mjs';
const env=Object.fromEntries(readFileSync('.env','utf8').split(/\r?\n/).filter(l=>l.includes('=')&&!l.startsWith('#')).map(l=>{const i=l.indexOf('=');return[l.slice(0,i),l.slice(i+1).replace(/^["']|["']$/g,'')]}));
assert.equal(env.LLM_MODE??'scripted','scripted','Live gate does not authorize paid calls');
const origin=env.APP_ORIGIN??'http://127.0.0.1:8091';assert(['http://127.0.0.1:8091','http://localhost:8091'].includes(origin));
const browser=await chromium.launch({headless:true,...(process.platform==='win32'?{channel:'msedge'}:{})});
const checks=[];
try{
 const context=await browser.newContext({baseURL:origin});const page=await context.newPage();page.setDefaultTimeout(30000);
 await page.goto('/');await page.getByRole('link',{name:'Sign in',exact:true}).click();await page.locator('#username').fill('demo');await page.locator('#password').fill(env.OIDC_DEMO_PASSWORD);await page.locator('#kc-login').click();await page.getByLabel('Tenant',{exact:true}).selectOption('aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa');await page.getByTestId('model-mode').waitFor();
 await page.getByLabel('What needs attention?').fill('Status GreenShop');await page.getByRole('button',{name:'Start investigation',exact:true}).click();
 await page.waitForURL(u=>u.searchParams.has('run_id'));const id=new URL(page.url()).searchParams.get('run_id');
 let value;for(let n=0;n<100;n++){value=await(await page.request.get(`/api/v2/runs/${id}`)).json();if(['completed','failed','cancelled','needs_attention'].includes(value.status))break;await page.waitForTimeout(300)}
 assert.equal(value.status,'completed');assert.equal(value.outcome,'diagnosis_only');assert.equal(value.mode,'scripted');assert.equal(value.usage.cost_usd,0);assert.equal(value.usage.cost_status,'known');assert.equal(value.usage.cached_input_tokens,0);assert.equal(value.usage.unknown_usage_count,0);assert(value.usage.llm_calls>0);assert(value.usage.read_calls>0);checks.push('real OIDC + worker completes scripted status run; durable usage / zero API cost');
 await page.getByTestId('model-cost').waitFor();assert.equal(await page.getByTestId('model-cost').innerText(),'0.000000');await page.reload();await page.getByTestId('model-cost').waitFor();const after=await(await page.request.get(`/api/v2/runs/${id}`)).json();assert.equal(after.usage.llm_calls,value.usage.llm_calls);assert.equal(after.usage.read_calls,value.usage.read_calls);assert.equal(after.usage.cost_usd,0);checks.push('browser refresh preserves usage / honest displayed cost');
 await page.getByRole('button',{name:'History',exact:true}).click();await page.getByRole('heading',{name:'Investigation history'}).waitFor();checks.push('existing authorized history remains usable');await page.getByRole('button',{name:'Diagnostics',exact:true}).click();
 await page.getByRole('heading',{name:'Operator diagnostics',exact:true}).waitFor();
 await page.getByLabel('Diagnostic run ID').fill(id);await page.getByRole('button',{name:'Refresh diagnostics',exact:true}).click();
 await page.getByTestId('collector-status').filter({hasText:'Available'}).waitFor();
 const diagnostics=await(await page.request.get('/api/v2/runs/'+id+'/diagnostics')).json();
 assert(diagnostics.collector.available);assert.equal(diagnostics.collector.integrity,'verified');
 for(let n=0;n<30&&!diagnostics.collector.events.some(e=>e.name==='command.process');n++){
   await page.waitForTimeout(300);Object.assign(diagnostics,await(await page.request.get('/api/v2/runs/'+id+'/diagnostics')).json());
 }
 assert(diagnostics.collector.events.some(e=>e.name==='command.process'));
 assert(diagnostics.database.jobs.some(j=>j.traceparent));checks.push('real OIDC diagnostics: live scoped DB + verified collector + durable command trace');
 await page.reload();await page.getByRole('heading',{name:'Operator diagnostics',exact:true}).waitFor();
 await page.getByTestId('collector-status').filter({hasText:'Available'}).waitFor();
 await page.screenshot({path:'.tools/f16-diagnostics.png',fullPage:true});
 await context.close();
 const report={passed:true,checks,run_id:id,usage:value.usage,real_oidc:true,synthetic:true,paid_calls:0,vendor_writes:0};writeFileSync('docs/full/evidence/f16/live-diagnostics.json',JSON.stringify(report,null,2)+'\n');console.log(JSON.stringify(report));
}finally{await browser.close()}

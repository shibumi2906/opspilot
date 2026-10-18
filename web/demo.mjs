import { chromium, expect } from '@playwright/test';
import fs from 'node:fs/promises';
const output = '/tmp/opspilot-demo';
await fs.mkdir(output, {recursive:true});
const started = Date.now();
const browser = await chromium.launch({headless:true});
const context = await browser.newContext({viewport:{width:1440,height:1000}, recordVideo:{dir:output,size:{width:1440,height:1000}}});
const page = await context.newPage();
const base = process.env.DEMO_BASE_URL ?? 'http://web';
const hold = ms => new Promise(resolve=>setTimeout(resolve,ms));
async function caption(text) {
  await page.evaluate(text=>{
    let element=document.getElementById('demo-caption');
    if(!element){element=document.createElement('div');element.id='demo-caption';document.body.append(element);}
    element.style.cssText='position:fixed;bottom:20px;left:50%;transform:translateX(-50%);z-index:10000;background:#102a28;color:#fff;padding:18px 26px;border:1px solid #83b9ad;border-radius:14px;font:500 18px system-ui;max-width:1050px;text-align:center;box-shadow:0 6px 35px #0003';
    element.textContent=text;
  },text);
}
async function screenshot(name){await page.evaluate(()=>{document.getElementById('demo-caption')?.remove();scrollTo({top:0,behavior:'instant'});}); await page.screenshot({path:`${output}/${name}.png`,fullPage:true});}
async function snapshot(){return await (await page.request.get(`${base}/api/v1/runs/${new URL(page.url()).searchParams.get('run_id')}`)).json();}
await page.goto(base);
await expect(page.getByTestId('model-mode')).toHaveText('Scripted model');
await screenshot('workspace');
await caption('OpsPilot: AI proposes. A deterministic core controls execution. Synthetic data; scripted model for this recording.');
await hold(14000);
await page.getByLabel('What needs attention?').fill('Investigate why GreenShop orders fail today');
await caption('One incident: GreenShop orders are failing. The graph collects evidence through real MCP tools.');
await hold(6000);
await page.getByRole('button',{name:'Start investigation',exact:true}).click();
await expect(page.getByRole('button',{name:'Approve & create ticket',exact:true})).toBeEnabled({timeout:60000});
const pending=await snapshot();
await page.locator('.source-button').first().click();
await caption('Current status, 401 events and expired credential metadata support a hypothesis. History and documentation provide context.');
await hold(14000);
await screenshot('evidence');
await page.getByTestId('ticket-title').scrollIntoViewIfNeeded();
await caption('The exact ticket fields are saved before approval. The model cannot authorize or execute this write.');
await hold(12000);
await screenshot('pending');
await caption('Hard restart: the API process is killed while this approval is pending. PostgreSQL keeps the checkpoint and immutable action.');
await fs.writeFile(`${output}/restart-ready`,pending.run_id);
console.log('RESTART_WINDOW',pending.run_id);
for(let i=0;i<120;i++){
  if(await fs.access(`${output}/restart-done`).then(()=>true,()=>false))break;
  if(i===119)throw new Error('Host restart confirmation missing');
  await hold(500);
}
await hold(8000);
await page.reload();
await expect(page.getByRole('button',{name:'Approve & create ticket',exact:true})).toBeEnabled({timeout:60000});
const restored=await snapshot();
if(restored.action.action_id!==pending.action.action_id||restored.action.arguments_hash!==pending.action.arguments_hash)throw new Error('Restored action differs');
await page.getByTestId('ticket-title').scrollIntoViewIfNeeded();
await caption('After restart: the same run, action ID and approved-payload hash. No new consent or replacement action is invented.');
await hold(14000);
await page.getByRole('button',{name:'Approve & create ticket',exact:true}).click();
await expect(page.getByRole('heading',{name:'Ticket verified.',exact:true})).toBeVisible({timeout:60000});
await page.getByRole('heading',{name:'Ticket verified.',exact:true}).scrollIntoViewIfNeeded();
await screenshot('verified');
const verified=await snapshot();
if(verified.outcome!=='actions_verified')throw new Error('Not verified');
await caption('Approve creates one ticket through MCP. get_ticket verifies every saved field. This does not restore order delivery.');
await hold(18000);
await page.getByRole('button',{name:/New investigation/}).click();
await page.getByLabel('What needs attention?').fill('Investigate GreenShop');
await page.getByRole('button',{name:'Start investigation',exact:true}).click();
await expect(page.getByRole('button',{name:'Reject action',exact:true})).toBeEnabled({timeout:60000});
await page.getByTestId('ticket-title').scrollIntoViewIfNeeded();
await caption('Alternative branch: Reject. The same policy boundary keeps the proposed write unexecuted.');
await hold(12000);
await page.getByRole('button',{name:'Reject action',exact:true}).click();
await expect(page.getByRole('heading',{name:'Decision respected.',exact:true})).toBeVisible({timeout:60000});
const rejected=await snapshot();
if(rejected.outcome!=='rejected'||rejected.action.result!==null)throw new Error('Reject wrote a ticket');
await page.getByRole('heading',{name:'Decision respected.',exact:true}).scrollIntoViewIfNeeded();
await screenshot('rejected');
await caption('Rejected: no execution result, no ticket. Evidence and the saved decision remain reviewable.');
await hold(14000);
await caption('AI layer: interpret and propose. Core: validate, persist, authorize and verify. Human: decide.');
const elapsed=(Date.now()-started)/1000;
if(elapsed<130)await hold((130-elapsed)*1000);
await hold(5000);
const video=page.video();
await context.close();
await video.saveAs(`${output}/opspilot-demo.webm`);
await browser.close();
await fs.writeFile(`${output}/metadata.json`,JSON.stringify({duration_seconds:(Date.now()-started)/1000,mode:'scripted',synthetic:true,hard_restart:true,verified_run:verified.run_id,rejected_run:rejected.run_id},null,2));
console.log('DEMO_COMPLETE');

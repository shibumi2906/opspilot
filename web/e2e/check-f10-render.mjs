import {createServer} from 'vite';
import {chromium} from '@playwright/test';
import {writeFile, mkdir} from 'node:fs/promises';
const server=await createServer({root:process.cwd(),server:{host:'127.0.0.1',port:18092,strictPort:true}});
await server.listen();
let browser;
try {
  browser=await chromium.launch({executablePath:process.env.F10_CHROMIUM_EXECUTABLE});
  const page=await browser.newPage();
  await page.goto('http://127.0.0.1:18092/e2e/approval-fixture.html');
  await page.waitForFunction(()=>typeof window.renderApproval==='function');
  const body='<img src=x onerror="window.pwned=1"><script>window.pwned=1</script> javascript:alert(1)';
  const results=[];
  for(const kind of ['add_ticket_comment','notify_manager']) {
    const target=kind==='add_ticket_comment'?'ticket_id':'recipient_id';
    const action={action_id:'synthetic-operation',tool_name:kind,arguments:{customer_id:'synthetic-customer',[target]:'synthetic-target',body,evidence_ids:['synthetic:evidence']},arguments_hash:'synthetic-hash',expected_version:1,expires_at:new Date(Date.now()+60000).toISOString(),approval_status:'pending',execution_status:'not_started',verification:{status:'not_started'},result:null};
    await page.evaluate(action=>window.renderApproval(action),action);
    await page.getByTestId('operation-body').waitFor();
    if(await page.getByTestId('operation-body').textContent()!==body) throw Error('Body changed');
    if(await page.getByTestId('approval-card').locator('img,script,a[href^="javascript:"]').count()) throw Error('Active content created');
    if(await page.evaluate(()=>window.pwned)) throw Error('XSS executed');
    if(!await page.getByTestId('approval-card').getByText('synthetic-target',{exact:true}).count()) throw Error('Exact target missing');
    results.push({tool:kind,body_exact:true,target_visible:true,active_content:false,xss_executed:false});
  }
  await mkdir('../docs/full/evidence/f10',{recursive:true});
  await writeFile('../docs/full/evidence/f10/render.json',JSON.stringify({scope:'Real Chromium component rendering via local Vite; no API/auth/DB acceptance claim',results},null,2));
  console.log(JSON.stringify(results));
} finally {await browser?.close();await server.close();}

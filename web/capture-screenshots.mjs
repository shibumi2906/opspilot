import { chromium, expect } from '@playwright/test';
import fs from 'node:fs/promises';
const output='/tmp/screenshots';await fs.mkdir(output,{recursive:true});
const browser=await chromium.launch();const page=await browser.newPage({viewport:{width:1440,height:1000}});
const base='http://web';
async function shot(name){await page.evaluate(()=>scrollTo({top:0,behavior:'instant'}));await page.waitForTimeout(200);await page.screenshot({path:`${output}/${name}.png`,fullPage:true});}
async function start(){await page.goto(base);await page.getByLabel('What needs attention?').fill('Investigate why GreenShop orders fail today');await page.getByRole('button',{name:'Start investigation',exact:true}).click();await expect(page.getByRole('button',{name:'Approve & create ticket',exact:true})).toBeEnabled({timeout:60000});}
await page.goto(base);await expect(page.getByTestId('model-mode')).toHaveText('Scripted model');await shot('workspace');
await start();await shot('pending');await page.locator('.source-button').filter({hasText:'Credential Status'}).click();await shot('evidence');
await page.getByRole('button',{name:'Approve & create ticket',exact:true}).click();await expect(page.getByRole('heading',{name:'Ticket verified.',exact:true})).toBeVisible({timeout:60000});await shot('verified');
await start();await page.getByRole('button',{name:'Reject action',exact:true}).click();await expect(page.getByRole('heading',{name:'Decision respected.',exact:true})).toBeVisible({timeout:60000});await shot('rejected');
await browser.close();

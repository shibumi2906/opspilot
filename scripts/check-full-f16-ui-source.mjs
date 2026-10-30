import {readFileSync,writeFileSync,readdirSync} from 'node:fs';import{createHash}from'node:crypto';
const files=[];function walk(base){for(const e of readdirSync('/work/'+base,{withFileTypes:true})){const p=base+'/'+e.name;if(e.isDirectory())walk(p);else files.push(p)}}
for(const root of ['web/src','web/e2e','tests/e2e'])walk(root);
files.push('web/index.html','web/package.json','web/package-lock.json','web/playwright.config.ts');
const hashes={};for(const name of files){const a=readFileSync('/work/'+name,'utf8').replace(/\r\n/g,'\n');const b=readFileSync('/app/'+name,'utf8').replace(/\r\n/g,'\n');if(a!==b)throw Error('Source mismatch '+name);hashes[name]=createHash('sha256').update(a).digest('hex')}
writeFileSync('/reports/ui-source-match.json',JSON.stringify({matched:true,files:files.length,sources:hashes},null,2)+'\n');console.log('UI/browser image sources match',files.length);

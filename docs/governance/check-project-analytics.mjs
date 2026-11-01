#!/usr/bin/env node
// Portable project gate. Generated copies retain their canonical source digest.
import {readFile,realpath} from 'node:fs/promises';import {resolve,relative,isAbsolute} from 'node:path';import {createHash} from 'node:crypto';
import {validateManifest} from './check-analytics-governance.mjs';
const args=process.argv.slice(2),preflight=args.includes('--preflight');
if(args.some(v=>!['--preflight'].includes(v)))throw Error('unsupported_arguments');
const root=await realpath(process.cwd());
const within=path=>{const rel=relative(root,path);return !isAbsolute(rel)&&rel!=='..'&&!rel.startsWith('..\\')&&!rel.startsWith('../');};
let policy;try{policy=JSON.parse(await readFile(new URL('./analytics-policy.json',import.meta.url),'utf8'));}catch{policy=JSON.parse(await readFile(new URL('../registry/analytics-policy.json',import.meta.url),'utf8'));}
const m=JSON.parse(await readFile(resolve(root,'ANALYTICS_INTEGRATION.json'),'utf8')),issues=validateManifest(m,m.projectId,policy);
if(!['verified','exception','not-applicable',...(preflight?['configured']:[])].includes(m.status))issues.push('integration not ready for this phase');
if(m.level==='business'&&!m.events?.length)issues.push('business journey contract missing');
if(!m.sites?.length&&!m.events?.length)issues.push('measurement scope missing');
if(m.status==='verified'){
 try{const path=await realpath(resolve(root,m.verification.evidenceFile));if(!within(path)||(await readFile(path,'utf8')).trim()==='')issues.push('evidence invalid');}catch{issues.push('evidence missing');}
}
try{const sources=JSON.parse(await readFile(resolve(root,'docs/governance/SOURCES.json'),'utf8'));if(sources.projectId!==m.projectId)issues.push('project identity differs from generated registry binding');for(const entry of sources.sources){if(!/^[a-zA-Z0-9.-]+$/.test(entry.target))throw Error();const path=await realpath(resolve(root,'docs/governance',entry.target));if(!within(path))throw Error();const data=await readFile(path);if(createHash('sha256').update(data).digest('hex')!==entry.sha256)issues.push('governance snapshot drift');}}catch{issues.push('versioned governance snapshots missing or invalid');}
console.log(JSON.stringify({projectId:m.projectId,phase:preflight?'configuration-preflight':'verified-delivery',status:m.status,passed:issues.length===0,issues}));if(issues.length)process.exitCode=1;

'use strict';
// Verification branch only. No user sessions, patient inputs or production API calls.
const fs=require('node:fs'),path=require('node:path'),os=require('node:os'),cp=require('node:child_process'),crypto=require('node:crypto');
const sha=p=>crypto.createHash('sha256').update(fs.readFileSync(p)).digest('hex');
async function main(){
 if(process.env.CASEFLOW_SPACING_QA!=='1')throw Error('Explicit hosted verification opt-in required');
 const out=path.resolve('.spacing-qa');fs.mkdirSync(out,{recursive:true});
 const summary={pass:false,complete:false,sourceSha256:sha('caseflow_studio_v96.html'),commit:process.env.VERCEL_GIT_COMMIT_SHA,versions:{chromium:'131.0.1',playwright:'1.57.0'},syntheticOnly:true,outcomes:[]};
 const run=(name,args,env={})=>{const r=cp.spawnSync(process.execPath,args,{env:{...process.env,...env},encoding:'utf8',timeout:120000,maxBuffer:8*1024*1024});fs.writeFileSync(path.join(out,name+'.log'),(r.stdout||'')+(r.stderr||''));summary.outcomes.push({name,pass:r.status===0,exitCode:r.status,error:r.error?.message||null});};
 try{
  run('spacing-unit',['scripts/verify-spacing-simulation.mjs']);run('mask-regression',['scripts/verify-spacing-mask-repair.mjs']);run('access-recovery',['scripts/verify-access-recovery.mjs']);
  const work=fs.mkdtempSync(path.join(os.tmpdir(),'caseflow-spacing-'));
  const install=cp.spawnSync('npm',['install','--prefix',work,'--ignore-scripts','--no-audit','--no-fund','--save=false','@sparticuz/chromium@131.0.1','playwright-core@1.57.0'],{encoding:'utf8',timeout:180000,maxBuffer:8*1024*1024});
  fs.writeFileSync(path.join(out,'install.log'),(install.stdout||'')+(install.stderr||''));if(install.status!==0)throw Error('Pinned browser dependency installation failed');
  const adapter=path.join(work,'adapter.cjs');fs.writeFileSync(adapter,`const chromium=require('./node_modules/@sparticuz/chromium');const unpack=require('./node_modules/@sparticuz/chromium/build/lambdafs').default;const path=require('node:path'),pw=require('./node_modules/playwright-core');module.exports={chromium:{launch:async(options={})=>{await unpack.inflate(path.join(__dirname,'node_modules/@sparticuz/chromium/bin/al2023.tar.br'));return pw.chromium.launch({...options,args:chromium.args,executablePath:await chromium.executablePath(),env:{...process.env,LD_LIBRARY_PATH:'/tmp/al2023/lib:'+(process.env.LD_LIBRARY_PATH||'')}});}}};`);
  run('native-canvas',['scripts/verify-spacing-canvas.mjs'],{CF_PLAYWRIGHT_MODULE:adapter,CF_CANVAS_SCREENSHOT:path.join(out,'canvas.png')});
  summary.complete=true;summary.pass=summary.outcomes.every(o=>o.pass);
 }catch(e){summary.error=String(e);}
 fs.writeFileSync(path.join(out,'summary.json'),JSON.stringify(summary,null,2));
 fs.writeFileSync(path.join(out,'index.html'),'<meta name="viewport" content="width=device-width"><h1>Caseflow synthetic verification</h1><pre>'+JSON.stringify(summary,null,2).replace(/</g,'&lt;')+'</pre><img style="max-width:100%" src="canvas.png">');
 if(fs.existsSync(path.join(out,'canvas.png')))fs.writeFileSync(path.join(out,'canvas.png.json'),JSON.stringify({mimeType:'image/png',encoding:'base64',data:fs.readFileSync(path.join(out,'canvas.png')).toString('base64')}));
 console.log('CASEFLOW SPACING VERIFICATION',JSON.stringify(summary));
 // Publish failure evidence; READY alone is deliberately not a test-pass signal.
}
main().catch(e=>{console.error(e);process.exitCode=1;});

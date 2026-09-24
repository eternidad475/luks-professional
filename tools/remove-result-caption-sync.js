const fs=require('fs');
const path='caseflow_studio_v96.html';
let s=fs.readFileSync(path,'utf8');
const before="    const cap=$id('resultCaption');\n    if(cap)cap.textContent=cfResultKindLabel(r,src)+' image / Reference Image — 説明用の参考イメージであり、治療結果の保証ではありません。';\n    cfDismissWaitVisualOnly();";
const after="    // Keep the first result paint image-only. The static clinical disclaimer already exists in HTML.\n    // Updating resultCaption here triggers a synchronous layout/observer chain on iOS/PWA.\n    cfDismissWaitVisualOnly();";
if(!s.includes(before))throw new Error('synchronous result caption anchor not found');
s=s.replace(before,after);
fs.writeFileSync(path,s);
console.log('removed synchronous result caption mutation');

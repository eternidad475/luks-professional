// CaseFlow Dev Console API
// Admin-only GitHub coding-agent scaffold for CaseFlow Studio.
// Vercel Serverless Function. No npm dependencies required.

const DEFAULT_REPO = process.env.CASEFLOW_DEV_REPO || "eternidad475/luks-professional";
const DEFAULT_BASE = process.env.CASEFLOW_DEV_BASE_BRANCH || "claude/image-morphing-video-3kujgb";
const DRY_RUN_ONLY = process.env.CASEFLOW_DEV_DRY_RUN_ONLY === "1";
const MAX_CONTEXT = Number(process.env.CASEFLOW_DEV_MAX_CONTEXT_CHARS || 70000);

function send(res, status, payload){
  res.statusCode = status;
  res.setHeader("content-type", "application/json; charset=utf-8");
  res.setHeader("cache-control", "no-store");
  res.end(JSON.stringify(payload, null, 2));
}

function readBody(req){
  return new Promise((resolve, reject)=>{
    let body = "";
    req.on("data", c => { body += c; if(body.length > 2000000){ reject(new Error("Request body too large")); req.destroy(); } });
    req.on("end", ()=>{ try{ resolve(body ? JSON.parse(body) : {}); }catch{ reject(new Error("Invalid JSON body")); } });
    req.on("error", reject);
  });
}

function token(){ return process.env.GITHUB_TOKEN || process.env.GH_TOKEN || ""; }
function admin(req){
  const key = process.env.CASEFLOW_DEV_CONSOLE_KEY || "";
  if(!key) return {ok:false, status:503, error:"CASEFLOW_DEV_CONSOLE_KEY is not configured."};
  const supplied = req.headers["x-caseflow-dev-key"] || req.headers["x-dev-agent-key"] || String(req.headers.authorization || "").replace(/^Bearer\s+/i, "");
  if(supplied !== key) return {ok:false, status:401, error:"Unauthorized. Provide the admin key."};
  return {ok:true};
}
function splitRepo(repo){ const [owner, name] = String(repo).split("/"); if(!owner || !name) throw new Error("repo must be owner/name"); return {owner, name}; }
function ep(s){ return String(s).split("/").map(encodeURIComponent).join("/"); }
async function gh(repo, method, path, body){
  if(!token()) throw new Error("GITHUB_TOKEN is not configured.");
  const {owner, name} = splitRepo(repo);
  const r = await fetch(`https://api.github.com/repos/${owner}/${name}${path}`, {
    method,
    headers:{
      accept:"application/vnd.github+json",
      "content-type":"application/json",
      "x-github-api-version":"2022-11-28",
      authorization:`Bearer ${token()}`,
      "user-agent":"caseflow-dev-console"
    },
    body: body ? JSON.stringify(body) : undefined
  });
  const t = await r.text(); let data = null; try{ data = t ? JSON.parse(t) : null; }catch{ data = {raw:t}; }
  if(!r.ok){ const e = new Error(data?.message || t || `${r.status} ${r.statusText}`); e.status = r.status; e.data = data; throw e; }
  return data;
}
async function ghGlobal(method, path, body){
  if(!token()) throw new Error("GITHUB_TOKEN is not configured.");
  const r = await fetch(`https://api.github.com${path}`, {
    method,
    headers:{accept:"application/vnd.github+json","content-type":"application/json","x-github-api-version":"2022-11-28",authorization:`Bearer ${token()}`,"user-agent":"caseflow-dev-console"},
    body: body ? JSON.stringify(body) : undefined
  });
  const t = await r.text(); let data = null; try{ data = t ? JSON.parse(t) : null; }catch{ data = {raw:t}; }
  if(!r.ok){ const e = new Error(data?.message || t || `${r.status} ${r.statusText}`); e.status = r.status; e.data = data; throw e; }
  return data;
}
function decode(file){ return file?.encoding === "base64" ? Buffer.from(file.content || "", "base64").toString("utf8") : (file?.content || ""); }
async function fetchFile(repo, path, ref){
  const q = ref ? `?ref=${encodeURIComponent(ref)}` : "";
  const f = await gh(repo, "GET", `/contents/${ep(path)}${q}`);
  return {path, sha:f.sha, size:f.size, html_url:f.html_url, content:decode(f)};
}
async function maybeFile(repo, path, ref){ try{ return await fetchFile(repo, path, ref); }catch(e){ if(e.status === 404) return null; throw e; } }
async function getRef(repo, branch){ return gh(repo, "GET", `/git/ref/${ep(`heads/${branch}`)}`); }
async function ensureBranch(repo, branch, base){
  try{ const x = await getRef(repo, branch); return {branch, existed:true, sha:x.object?.sha}; }catch(e){ if(e.status !== 404) throw e; }
  const b = await getRef(repo, base); const sha = b.object?.sha; if(!sha) throw new Error(`Could not resolve ${base}`);
  const c = await gh(repo, "POST", "/git/refs", {ref:`refs/heads/${branch}`, sha});
  return {branch, existed:false, sha:c.object?.sha || sha};
}
async function searchCode(repo, query){
  try{
    const q = encodeURIComponent(`${query} repo:${repo}`);
    const d = await ghGlobal("GET", `/search/code?q=${q}&per_page=8`);
    return (d.items || []).map(i => ({name:i.name, path:i.path, score:i.score, html_url:i.html_url}));
  }catch(e){ return [{name:"search-unavailable", path:"search-unavailable", error:e.message}]; }
}
function latest(messages){ const m = Array.isArray(messages) ? messages[messages.length-1] : null; return String(m?.content || m?.text || ""); }
function terms(text){
  const words = String(text).replace(/[^\p{L}\p{N}_\-./ ]/gu," ").split(/\s+/).filter(Boolean).filter(w => w.length > 2);
  return Array.from(new Set(["caseflow_studio_v96.html", "CaseFlow", "Morphing", "Visual", ...words])).slice(0,8);
}
async function context(repo, base, messages, explicitPaths){
  const searches = []; const paths = new Set((explicitPaths || []).filter(Boolean));
  for(const term of terms(latest(messages)).slice(0,5)){
    const hits = await searchCode(repo, term); searches.push({term, hits});
    for(const h of hits.slice(0,2)) if(h.path && h.path !== "search-unavailable") paths.add(h.path);
  }
  paths.add("caseflow_studio_v96.html");
  let remain = MAX_CONTEXT; const files = [];
  for(const path of Array.from(paths).slice(0,8)){
    try{
      const f = await fetchFile(repo, path, base); let content = f.content || "";
      if(content.length > remain) content = content.slice(0, Math.max(0, remain)) + "\n\n/* [TRUNCATED BY CASEFLOW DEV CONSOLE] */";
      remain -= content.length; files.push({...f, content}); if(remain <= 0) break;
    }catch(e){ files.push({path, error:e.message}); }
  }
  return {searches, files};
}
function parseJson(text){
  if(!text) return null; const s = String(text).trim();
  try{return JSON.parse(s);}catch{}
  const fence = s.match(/```(?:json)?\s*([\s\S]*?)```/i); if(fence){ try{return JSON.parse(fence[1]);}catch{} }
  const a = s.indexOf("{"); const b = s.lastIndexOf("}"); if(a >= 0 && b > a){ try{return JSON.parse(s.slice(a,b+1));}catch{} }
  return null;
}
function setup(ctx){
  return {summary:"Dev Console scaffold is installed, but no AI provider is configured yet.",summary_ja:"Dev Consoleの土台は追加済みですが、AIプロバイダーが未設定です。",plan:["Set CASEFLOW_DEV_CONSOLE_KEY and GITHUB_TOKEN.","Set ANTHROPIC_API_KEY + ANTHROPIC_MODEL or OPENAI_API_KEY + OPENAI_MODEL.","Use dry-run first."],plan_ja:["CASEFLOW_DEV_CONSOLE_KEY と GITHUB_TOKEN を設定する。","ANTHROPIC_API_KEY + ANTHROPIC_MODEL、または OPENAI_API_KEY + OPENAI_MODEL を設定する。","最初はdry-runで使う。"],actions:[],context:ctx};
}
async function anthropic(system, payload){
  if(!process.env.ANTHROPIC_API_KEY || !process.env.ANTHROPIC_MODEL) return null;
  const r = await fetch("https://api.anthropic.com/v1/messages", {method:"POST",headers:{"content-type":"application/json","x-api-key":process.env.ANTHROPIC_API_KEY,"anthropic-version":"2023-06-01"},body:JSON.stringify({model:process.env.ANTHROPIC_MODEL,max_tokens:4000,temperature:.2,system,messages:[{role:"user",content:JSON.stringify(payload)}]})});
  const d = await r.json(); if(!r.ok) throw new Error(d?.error?.message || "Anthropic request failed");
  return d.content?.map(p => p.text || "").join("\n") || "";
}
async function openai(system, payload){
  if(!process.env.OPENAI_API_KEY || !process.env.OPENAI_MODEL) return null;
  const r = await fetch("https://api.openai.com/v1/responses", {method:"POST",headers:{"content-type":"application/json",authorization:`Bearer ${process.env.OPENAI_API_KEY}`},body:JSON.stringify({model:process.env.OPENAI_MODEL,input:[{role:"system",content:system},{role:"user",content:JSON.stringify(payload)}],temperature:.2})});
  const d = await r.json(); if(!r.ok) throw new Error(d?.error?.message || "OpenAI request failed");
  if(typeof d.output_text === "string") return d.output_text;
  return (d.output || []).flatMap(i => i.content || []).map(p => p.text || p.content || "").join("\n");
}
async function model(payload){
  const system = `You are CaseFlow Dev Console, a careful coding agent for CaseFlow Studio. Return ONLY valid JSON with this schema: {"summary":"English", "summary_ja":"日本語", "plan":["English"], "plan_ja":["日本語"], "risk_notes":["English"], "risk_notes_ja":["日本語"], "actions":[{"type":"create_file|update_file", "path":"relative/path", "content":"complete UTF-8 file", "commitMessage":"message"}], "pr":{"title":"title", "body":"markdown"}}. Never expose secrets or patient data. Never push to base/main. For huge files, prefer a plan unless enough context exists. CaseFlow Studio has Photo Manager, Visual Simulation Studio, and Morphing Video Studio; UI safety is critical.`;
  const a = await anthropic(system, payload); if(a) return parseJson(a) || {raw:a};
  const o = await openai(system, payload); if(o) return parseJson(o) || {raw:o};
  return setup(payload.context);
}
function actions(result){
  return (Array.isArray(result?.actions) ? result.actions : []).filter(a => a && ["create_file","update_file"].includes(a.type) && typeof a.path === "string" && typeof a.content === "string").map(a => ({type:a.type,path:a.path.replace(/^\/+/,""),content:a.content,commitMessage:a.commitMessage || `dev-console: ${a.type} ${a.path}`}));
}
async function apply(repo, branch, acts){
  const out = [];
  for(const a of acts){
    const cur = await maybeFile(repo, a.path, branch);
    if(a.type === "create_file" && cur) throw new Error(`Refusing to create existing file: ${a.path}`);
    if(a.type === "update_file" && !cur) throw new Error(`Refusing to update missing file: ${a.path}`);
    const body = {message:a.commitMessage, content:Buffer.from(a.content,"utf8").toString("base64"), branch};
    if(cur?.sha) body.sha = cur.sha;
    const d = await gh(repo, "PUT", `/contents/${ep(a.path)}`, body);
    out.push({type:a.type,path:a.path,commit:d.commit?.sha,html_url:d.content?.html_url});
  }
  return out;
}
async function pr(repo, head, base, result){
  return gh(repo, "POST", "/pulls", {title:result?.pr?.title || "feat: add CaseFlow Dev Console update", body:result?.pr?.body || "Generated by CaseFlow Dev Console.\n\nDraft PR only. No direct base-branch push.", head, base, draft:true, maintainer_can_modify:true});
}
async function chat(payload){
  const repo = payload.repo || DEFAULT_REPO;
  const base = payload.baseBranch || DEFAULT_BASE;
  const branch = payload.branch || `dev-console/${new Date().toISOString().slice(0,10).replace(/-/g,"")}`;
  const doApply = Boolean(payload.apply) && !DRY_RUN_ONLY;
  const ctx = await context(repo, base, payload.messages || [], payload.paths || []);
  const result = await model({repo, baseBranch:base, branch, apply:doApply, messages:payload.messages || [], context:ctx});
  const acts = actions(result);
  const response = {ok:true, mode:doApply ? "apply" : "dry-run", repo, baseBranch:base, branch, modelResult:result, actions:acts, applied:[], pullRequest:null, dryRunOnly:DRY_RUN_ONLY};
  if(doApply && acts.length){
    response.branchStatus = await ensureBranch(repo, branch, base);
    response.applied = await apply(repo, branch, acts);
    const p = await pr(repo, branch, base, result);
    response.pullRequest = {number:p.number, url:p.html_url, title:p.title, draft:p.draft};
  }
  return response;
}
async function health(){ return {ok:true, app:"CaseFlow Dev Console", repo:DEFAULT_REPO, baseBranch:DEFAULT_BASE, dryRunOnly:DRY_RUN_ONLY, env:{githubToken:Boolean(token()), adminKey:Boolean(process.env.CASEFLOW_DEV_CONSOLE_KEY), anthropic:Boolean(process.env.ANTHROPIC_API_KEY && process.env.ANTHROPIC_MODEL), openai:Boolean(process.env.OPENAI_API_KEY && process.env.OPENAI_MODEL)}}; }

module.exports = async function handler(req, res){
  if(req.method === "OPTIONS") return send(res, 204, {});
  if(req.method !== "POST") return send(res, 405, {ok:false, error:"Method not allowed"});
  const a = admin(req); if(!a.ok) return send(res, a.status, {ok:false, error:a.error});
  try{
    const payload = await readBody(req);
    const action = payload.action || "chat";
    if(action === "health") return send(res, 200, await health());
    if(action === "search") return send(res, 200, {ok:true, repo:payload.repo || DEFAULT_REPO, query:payload.query || latest(payload.messages) || "CaseFlow", hits:await searchCode(payload.repo || DEFAULT_REPO, payload.query || latest(payload.messages) || "CaseFlow")});
    if(action === "read_file") return send(res, 200, {ok:true, ...(await fetchFile(payload.repo || DEFAULT_REPO, payload.path, payload.ref || payload.baseBranch || DEFAULT_BASE))});
    if(action === "chat") return send(res, 200, await chat(payload));
    throw new Error(`Unknown action: ${action}`);
  }catch(e){ return send(res, e.status || 500, {ok:false, error:e.message, data:e.data || null}); }
};

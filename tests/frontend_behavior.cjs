const {readFileSync}=require('node:fs');
const {resolve}=require('node:path');
const vm=require('node:vm');
const assert=require('node:assert/strict');
const nodes=new Map();
function node(tag='div'){
 return {tagName:tag,textContent:'',value:'',hidden:false,disabled:false,content:'token',dataset:{},children:[],
 get options(){return this.children;},
 replaceChildren(...items){this.children=[];this.append(...items);},
 append(...items){for(const item of items){item.parent=this;this.children.push(item);}},
 insertBefore(item,before){if(item.parent)item.remove();const i=before?this.children.indexOf(before):-1;item.parent=this;this.children.splice(i<0?this.children.length:i,0,item);},
 remove(){if(this.parent){this.parent.children=this.parent.children.filter(x=>x!==this);this.parent=null;}},
 add(item){this.append(item);},setAttribute(){},addEventListener(){},focus(){},
 querySelector(selector){return this.children.find(n=>selector==='[data-elapsed]'?'elapsed' in n.dataset:n.tagName===selector)||this.children.map(n=>n.querySelector(selector)).find(Boolean)||null;}};
}
const requests=[];let response;
const context=vm.createContext({document:{getElementById(id){if(!nodes.has(id))nodes.set(id,node());return nodes.get(id);},querySelector(){return {content:'token',addEventListener(){}};},createElement(tag){return node(tag);}},location:{origin:'http://localhost:8000'},Option:function(label,value){const n=node('option');n.textContent=label;n.value=value;return n;},URL,Date,Map,Set,Array,JSON,Number,String,Error,crypto:{randomUUID:()=> 'fixed-request-id'},sessionStorage:{setItem(){},removeItem(){}},window:{confirm:()=>false},fetch:async(path,options)=>{requests.push({path,options});return response();}});
const source=readFileSync(resolve(__dirname, '../src/automusic/static/web/app.js'),'utf8');
vm.runInContext(source.slice(0,source.indexOf('$("category").addEventListener')),context);
async function run(code){return vm.runInContext(code,context);}
(async()=>{
// Sidebar reuses each existing GET, replaces stale success on failure, and recovers.
const sidebarStart=requests.length;
response=()=>({ok:true,json:async()=>({items:[{id:'side-job',status:'generating_music'},{id:'side-queued',status:'queued'}]})});
await run('loadJobs()');
assert.equal(await run('$("sidebar-generation").textContent'),'생성 진행 2개');
response=()=>{throw new Error('offline');};await run('loadJobs()');
assert.equal(await run('$("sidebar-generation").textContent'),'확인 불가');
response=()=>({ok:true,json:async()=>({items:[]})});await run('loadJobs()');
assert.equal(await run('$("sidebar-generation").textContent'),'진행 작업 없음');
assert.deepEqual(requests.slice(sidebarStart).map(r=>r.path),['/api/jobs','/api/jobs','/api/jobs']);
const sidebarSchedulerStart=requests.length;
response=()=>({ok:true,json:async()=>({state:'enabled',supported:true,installed:true,registered:true,enabled:true,observed_at:'2026-10-23T01:02:03Z'})});
await run('loadScheduler()');
assert.equal(await run('$("sidebar-scheduler").textContent'),'켜짐');
assert.equal(await run('$("sidebar-scheduler-updated").textContent'),await run('"마지막 확인 " + dateLabel("2026-10-23T01:02:03Z")'));
response=()=>{throw new Error('offline');};await run('loadScheduler()');
assert.equal(await run('$("sidebar-scheduler").textContent'),'확인 불가');
assert.equal(await run('$("sidebar-scheduler-updated").textContent'),'마지막 확인 시각 정보 없음');
response=()=>({ok:true,json:async()=>({state:'disabled',supported:true,installed:true,registered:true,enabled:false,observed_at:'2026-10-23T02:03:04Z'})});
await run('loadScheduler()');
assert.equal(await run('$("sidebar-scheduler").textContent'),'꺼짐');
assert.equal(await run('$("sidebar-scheduler-updated").textContent'),await run('"마지막 확인 " + dateLabel("2026-10-23T02:03:04Z")'));
assert.deepEqual(requests.slice(sidebarSchedulerStart).map(r=>r.path),['/api/scheduler','/api/scheduler','/api/scheduler']);
// Regression: clock refreshes stay outside live messages; actual status changes remain visible.
response=()=>({ok:true,json:async()=>({items:[{id:'j',status:'queued'}]})});
await run('loadJobs()');
assert.doesNotMatch(await run('$("jobs-message").textContent'),/마지막 조회/);
assert.match(await run('$("jobs-updated").textContent'),/마지막 조회/);
const queuedMessage=await run('$("jobs-message").textContent');
await run('loadJobs()');assert.equal(await run('$("jobs-message").textContent'),queuedMessage);
response=()=>({ok:true,json:async()=>({items:[{id:'j',status:'generating_music'}]})});
await run('loadJobs()');assert.notEqual(await run('$("jobs-message").textContent'),queuedMessage);
response=()=>({ok:true,json:async()=>({track_count:0,total_duration_seconds:0,active_jobs:[],recent_errors:[]})});
await run('loadDashboard()');assert.doesNotMatch(await run('$("dashboard-message").textContent'),/마지막 조회/);
assert.match(await run('$("dashboard-updated").textContent'),/마지막 조회/);
// Initial failure must never become an empty-library claim when filtering.
response=()=>{throw new Error('offline');};
await run('loadLibrary()');await run('$("library-search").value="missing";renderLibrary()');
assert.match(await run('$("library-message").textContent'),/연결하지 못했습니다/);
assert.doesNotMatch(await run('$("library-message").textContent'),/재생 가능한 음악이 없습니다/);
const song={id:'song',title:'곡 제목',variant_id:'piano',duration_seconds:30,created_at:'2026-10-23T00:00:00Z',model:'lyria-3.5',music_prompt:'full prompt',source:'web',audio_url:'/api/library/song/audio',download_url:'/api/library/song/download'};
context.song=song;
response=()=>({ok:true,json:async()=>({items:[song],unreadable_count:0})});
await run('$("library-search").value="";$("source-filter").value="all";loadLibrary()');
assert.doesNotMatch(await run('$("library-message").textContent'),/연결하지 못했습니다/);
const article=await run('$("library-list").children[0]');
assert.ok(article.querySelector('details').querySelector('p'));
assert.ok(!article.children.filter(n=>n.tagName==='p').some(n=>n.textContent.includes('lyria-3.5')));
assert.ok(article.querySelector('details').children.some(n=>n.textContent.includes('lyria-3.5')));
assert.equal(article.querySelector('audio').src,'http://localhost:8000/api/library/song/audio');
const player=article.querySelector('audio');await run('renderLibrary()');
assert.equal((await run('$("library-list").children[0]')).querySelector('audio'),player);
response=()=>{throw new Error('offline');};await run('loadLibrary()');await run('$("library-search").value="zzz";renderLibrary()');
assert.match(await run('$("library-message").textContent'),/연결하지 못했습니다/);
assert.match(await run('$("library-message").textContent'),/마지막으로|이전/);
response=()=>({ok:true,json:async()=>({items:[],unreadable_count:0})});await run('loadLibrary()');
assert.doesNotMatch(await run('$("library-message").textContent'),/연결하지 못했습니다/);
assert.match(await run('$("library-message").textContent'),/재생 가능한 음악이 없습니다/);
assert.equal(await run('safeURL("https://attacker.example/secret")'),null);
assert.equal(await run('safeURL("//attacker.example/api/audio")'),null);
assert.equal(await run('safeURL("/api/../private")'),null);
assert.equal(await run('safeURL("/api/jobs/123/audio")'),'http://localhost:8000/api/jobs/123/audio');
assert.equal(await run('duration(null)'),'길이 정보 없음');
assert.equal(await run('dateLabel("invalid")'),'시각 정보 없음');
await run('$("category").value="study";$("variant").value="random";$("job-status").textContent="미리보기를 먼저 확인하세요."');
response=()=>({ok:true,json:async()=>({id:'preview-ready',category_id:'study',variant_id:'minimal-piano-solo',prompt:'original prompt',details:{}})});
await run('preview()');
assert.equal(await run('$("job-status").textContent'),'확인한 프롬프트로 음악을 만들 준비가 됐습니다.');
await run('invalidatePreview()');
assert.equal(await run('$("job-status").textContent'),'미리보기를 먼저 확인하세요.');
await run('state.pending={jobId:"accepted-job"};$("job-status").textContent="대기 중";invalidatePreview()');
assert.equal(await run('$("job-status").textContent'),'대기 중','invalidating a preview must not overwrite accepted job status');
await run('state.pending=null');
requests.length=0;
await run('loadJobs=async()=>{};loadDashboard=async()=>{};state.preview={id:"preview-1"};$("music-prompt").value="edited prompt";');
response=()=>{throw new Error('offline');};
await run('createJob()');
assert.equal(await run('state.pending.body.request_id'),'fixed-request-id');
assert.equal(await run('$("create-job").disabled'),true);
assert.equal(await run('$("music-prompt").disabled'),true);
assert.match(await run('$("job-status").textContent'),/요청이 접수됐는지 확인이 필요합니다/);
const firstBody=requests.at(-1).options.body;
await run('createJob()');assert.equal(requests.length,1,'double submit must not issue request');
response=()=>({ok:true,json:async()=>({id:'job-1',status:'queued'})});
await run('submitPending()');
assert.equal(requests.at(-1).options.body,firstBody,'ambiguous retry must retain request and prompt');
assert.equal(requests.at(-1).options.headers['X-CSRF-Token'],'token');
assert.equal(await run('state.pending.jobId'),'job-1');
await run('state.scheduler={supported:true,installed:true,enabled:false,state:"disabled"};schedulerControls()');
assert.equal(await run('$("scheduler-enable").disabled'),false);
const before=requests.length;await run('setScheduler(true)');assert.equal(requests.length,before,'cancel must not change scheduler');
response=()=>{throw new Error('offline');};await run('loadScheduler()');
assert.equal(await run('$("scheduler-enable").disabled'),true);
assert.equal(await run('$("scheduler-disable").disabled'),true);
assert.equal(await run('state.scheduler?.state'),'unknown','network failure must replace stale scheduler state');
assert.equal(await run('sourceLabel("archived")'),'보관된 트랙');
assert.equal(await run('detailLabel([{intro:["piano","soft"]},{outro:"fade"}])'),'intro: piano, soft, outro: fade');
response=()=>({ok:false,status:503,json:async()=>({error:'일부 조회 실패',state:'partial_failure',installed:true,supported:true,enabled:null,schedule:{hour:9,minute:30}})});
await run('loadScheduler()');
assert.equal(await run('state.scheduler.state'),'partial_failure');
assert.equal(await run('$("sidebar-scheduler").textContent'),'확인 불가','partial failure must not appear enabled or disabled');
assert.equal(await run('state.scheduler.installed'),true);
assert.equal(await run('state.scheduler.schedule.hour'),9);
assert.equal(await run('$("scheduler-enable").disabled'),true);
for (const registered of [true,false]) {
for (const enabled of [true,false,null]) {
 await run(`state.scheduler={supported:true,installed:true,registered:${registered},enabled:${enabled},state:"partial_failure"};schedulerControls()`);
 assert.equal(await run('$("scheduler-enable").disabled'),false,'partial failure must allow enabling retry');
 assert.equal(await run('$("scheduler-disable").disabled'),false,'partial failure must allow disabling retry');
 assert.equal(await run('$("scheduler-enable").textContent'),'켜기 재시도');
 assert.equal(await run('$("scheduler-disable").textContent'),'끄기 재시도');
}
}
for (const flag of ['supported','installed','registered']) {
 for (const value of (flag === 'registered' ? [null] : [false,null])) {
  await run(`state.scheduler={supported:true,installed:true,registered:true,enabled:false,state:"partial_failure"};state.scheduler["${flag}"]=${value};schedulerControls()`);
  assert.equal(await run('$("scheduler-enable").disabled'),true);
  assert.equal(await run('$("scheduler-disable").disabled'),true);
 }
}
await run('state.scheduler={supported:true,installed:true,registered:false,enabled:false,state:"disabled"};schedulerControls()');
assert.equal(await run('$("scheduler-disable").disabled'),false,'confirmed unregistered disabled state must allow persistent disable');
await run('window.confirm=()=>true');
const disableStart=requests.length;
response=()=>({ok:true,json:async()=>({supported:true,installed:true,registered:false,enabled:false,state:'disabled'})});
await run('setScheduler(false)');
assert.equal(requests.length,disableStart+2);
assert.equal(JSON.parse(requests[disableStart].options.body).enabled,false);
await run('state.scheduler={supported:true,installed:true,registered:true,enabled:false,state:"disabled"};schedulerControls()');
assert.equal(await run('$("scheduler-disable").disabled'),true,'normal registered disabled state remains locked');
await run('state.scheduler={supported:true,installed:true,registered:true,enabled:true,state:"unknown"};schedulerControls()');
assert.equal(await run('$("scheduler-enable").disabled'),true);
assert.equal(await run('$("scheduler-disable").disabled'),true);
for (const registered of [true,false]) {
for (const target of [true,false]) {
 await run(`state.scheduler={supported:true,installed:true,registered:${registered},enabled:null,state:"partial_failure"};schedulerControls();window.confirm=()=>false`);
 const count=requests.length;await run(`setScheduler(${target})`);assert.equal(requests.length,count);
 await run('window.confirm=()=>true');
 response=()=>({ok:true,json:async()=>({supported:true,installed:true,registered:true,enabled:target,state:target?'enabled':'disabled'})});
 await run(`setScheduler(${target})`);
 assert.equal(requests.length,count+2,'explicit retry must POST and verify with GET');
 assert.equal(JSON.parse(requests[count].options.body).enabled,target);
 assert.equal(await run('state.scheduler.state'),target?'enabled':'disabled');
}
}
await run('document.querySelectorAll=()=>[];location.hash="#library";var libraryLoads=0;loadLibrary=async()=>{libraryLoads+=1};route()');
assert.equal(await run('libraryLoads'),1,'entering library must refresh');
await run('location.hash="#generate";route();var skipPrevented=false;var contentFocused=false;$("content").focus=()=>{contentFocused=true};skipToContent({preventDefault(){skipPrevented=true}});if(!skipPrevented){location.hash="#content";route()}');
assert.equal(await run('skipPrevented'),true,'skip link must prevent hash navigation');
assert.equal(await run('location.hash'),'#generate','skip link must preserve selected screen URL');
assert.equal(await run('$("generate").hidden'),false,'skip link must preserve generator');
assert.equal(await run('$("dashboard").hidden'),true,'skip link must not open dashboard');
assert.equal(await run('contentFocused'),true,'skip link must focus main content');
console.log('Design regression groups passed: non-live timestamps, status changes, persistent library errors, recovery, model details, audio node reuse. Partial-failure recovery and 14 baseline behavior groups passed: URL boundaries, null metadata, ambiguous acceptance, duplicate click, immutable retry, CSRF, accepted job, cancel, scheduler unknown, locks');
})().catch(e=>{console.error(e);process.exitCode=1;});

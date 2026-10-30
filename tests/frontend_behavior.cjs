const {readFileSync}=require('node:fs');
const {resolve}=require('node:path');
const vm=require('node:vm');
const assert=require('node:assert/strict');
const nodes=new Map();
function node(tag='div'){
 const listeners=new Map();const attributes=new Map();
 return {tagName:tag,textContent:'',value:'',hidden:false,disabled:false,content:'token',dataset:{},children:[],
 paused:true,currentTime:0,pauseCalls:0,
 pause(){this.pauseCalls+=1;this.paused=true;},
 play(){this.paused=false;this.dispatchEvent({type:'play'});},
 get options(){return this.children;},
 replaceChildren(...items){this.children=[];this.append(...items);},
 append(...items){for(const item of items){item.parent=this;this.children.push(item);}},
 insertBefore(item,before){if(item.parent)item.remove();const i=before?this.children.indexOf(before):-1;item.parent=this;this.children.splice(i<0?this.children.length:i,0,item);},
 remove(){if(this.parent){this.parent.children=this.parent.children.filter(x=>x!==this);this.parent=null;}},
 add(item){this.append(item);},setAttribute(name,value){attributes.set(name,value);},removeAttribute(name){attributes.delete(name);},getAttribute(name){return attributes.get(name)??null;},
 addEventListener(type,callback){if(!listeners.has(type))listeners.set(type,[]);listeners.get(type).push(callback);},
 dispatchEvent(event){for(const callback of listeners.get(event.type)||[])callback.call(this,event);},focus(){},
 querySelector(selector){return this.children.find(n=>selector==='[data-order]'?'order' in n.dataset:selector==='[data-elapsed]'?'elapsed' in n.dataset:n.tagName===selector)||this.children.map(n=>n.querySelector(selector)).find(Boolean)||null;}};
}
const requests=[];let response;
const navigation=['dashboard','generate','library','scheduler'].map(id=>Object.assign(node('a'),{hash:`#${id}`}));
const context=vm.createContext({document:{getElementById(id){if(!nodes.has(id))nodes.set(id,node());return nodes.get(id);},querySelector(){return {content:'token',addEventListener(){}};},createElement(tag){return node(tag);}},location:{origin:'http://localhost:8000'},Option:function(label,value){const n=node('option');n.textContent=label;n.value=value;return n;},URL,Date,Map,Set,Array,JSON,Number,String,Error,crypto:{randomUUID:()=> 'fixed-request-id'},sessionStorage:{setItem(){},removeItem(){}},window:{confirm:()=>false},fetch:async(path,options)=>{requests.push({path,options});return response();}});
const source=readFileSync(resolve(__dirname, '../src/automusic/static/web/app.js'),'utf8');
vm.runInContext(source.slice(0,source.indexOf('$("category").addEventListener')),context);
vm.runInContext('var originalLoadJobs = loadJobs; var originalLoadLibrary = loadLibrary',context);
async function run(code){return vm.runInContext(code,context);}
context.document.querySelectorAll=selector=>selector==='.navigation a'?navigation:[];
(async()=>{
// Pagination retains full data while displaying only the selected window.
assert.equal(await run('pageSlice("library", Array.from({length:21},(_,id)=>({id}))).length'),20);
await run('state.libraryPage=2');
assert.equal(await run('pageSlice("library", Array.from({length:21},(_,id)=>({id})))[0].id'),20);
await run('pageSlice("library", [] )');
assert.equal(await run('state.libraryPage'),1);
assert.equal(await run('$("library-next").disabled'),true);
assert.doesNotMatch(await run('$("library-range").textContent'),/1–0|0\/0/);
await run('state.librarySize=50');
assert.equal(await run('pageSlice("library", Array.from({length:51},(_,id)=>({id}))).length'),50);
await run('state.libraryPage=2');
assert.equal(await run('pageSlice("library", Array.from({length:51},(_,id)=>({id}))).length'),1);
await run('state.librarySize=100;state.libraryPage=1');
assert.equal(await run('pageSlice("library", Array.from({length:101},(_,id)=>({id}))).length'),100);
await run('state.librarySize=20;state.libraryPage=1');
assert.equal(await run('libraryCategoryLabel("fitness-metal")'), 'Fitness Metal');
assert.equal(await run('libraryCategoryLabel("fitness-rock")'), 'Fitness Rock');
assert.equal(await run('libraryCategoryLabel("jazz")'), 'Jazz');
assert.equal(await run('libraryCategoryLabel("sleep")'), 'Sleep');
assert.equal(await run('libraryCategoryLabel("japan-city-pop")'), 'Japan City Pop');
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
const article=await run('$("library-list").children.find(node=>node.tagName==="article")');
assert.ok(article.querySelector('details').querySelector('p'));
assert.ok(!article.children.filter(n=>n.tagName==='p').some(n=>n.textContent.includes('lyria-3.5')));
assert.ok(article.querySelector('details').children.some(n=>n.textContent.includes('lyria-3.5')));
assert.equal(article.querySelector('audio').src,'http://localhost:8000/api/library/song/audio');
const player=article.querySelector('audio');await run('renderLibrary()');
assert.equal((await run('$("library-list").children.find(node=>node.tagName==="article")')).querySelector('audio'),player);
context.groupSongs=[song,{...song,id:'study-song',category_id:'study'},{...song,id:'lofi-song',category_id:'lofi'}];
await run('state.library=groupSongs; renderLibrary()');
assert.equal(await run('$("library-list").children.filter(n=>n.dataset.categoryHeading!==undefined).length'),3);
await run('selectLibraryCategory("study")');
assert.equal(await run('$("library-list").children.length'),1);
assert.equal(await run('$("library-list").children[0].dataset.id'),'study-song');
await run('$("library-search").value="no match";renderLibrary()');
assert.equal(await run('$("library-list").children.length'),0);
await run('$("library-search").value="";selectLibraryCategory("")');
assert.equal(await run('$("library-list").children[0].dataset.id'),'song');
await run('selectLibraryCategory(null)');
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
await run('location.hash="#library";var libraryLoads=0;loadLibrary=async()=>{libraryLoads+=1};route()');
assert.equal(await run('libraryLoads'),1,'entering library must refresh');
// Exercise the actual media() listeners, not a duplicate playback implementation.
const playbackRequests=requests.length;
await run('var firstMedia=element("div");var secondMedia=element("div");media({audio_url:"/api/library/first/audio"},firstMedia);media({audio_url:"/api/library/second/audio"},secondMedia)');
const firstAudio=await run('firstMedia.querySelector("audio")');
const secondAudio=await run('secondMedia.querySelector("audio")');
assert.ok(firstAudio&&secondAudio,'media must create both audio players');
firstAudio.currentTime=12;firstAudio.play();
assert.equal(firstAudio.pauseCalls,0,'first play must not pause itself');
secondAudio.currentTime=8;secondAudio.play();
assert.equal(firstAudio.pauseCalls,1,'new audio must pause previous audio');
assert.equal(firstAudio.paused,true);
assert.equal(firstAudio.currentTime,12,'switching tracks preserves previous position');
assert.equal(secondAudio.paused,false);
secondAudio.play();
assert.equal(secondAudio.pauseCalls,0,'repeated play of same audio must not pause itself');
await run('route()');
assert.equal(secondAudio.pauseCalls,0,'same route preserves playback');
assert.equal(secondAudio.currentTime,8,'same route preserves playback position');
await run('location.hash="#generate";route()');
assert.equal(secondAudio.paused,true,'menu change pauses playback');
assert.equal(secondAudio.pauseCalls,1);
assert.equal(secondAudio.currentTime,0,'menu change resets playback position');
assert.equal(navigation[1].getAttribute('aria-current'),'page');
assert.equal(navigation[2].getAttribute('aria-current'),null);
await run('location.hash="#dashboard";route()');
assert.equal(secondAudio.pauseCalls,1,'later navigation must not pause an already cleared player');
firstAudio.play();
assert.equal(secondAudio.pauseCalls,1,'playing after navigation must not retain the previous player');
assert.equal(firstAudio.paused,false);
await run('location.hash="#generate";route()');
assert.equal(firstAudio.currentTime,0,'resumed playback also resets when leaving');
assert.equal(requests.length,playbackRequests,'playback and route checks must not introduce API requests');
console.log('Audio regression groups passed: exclusive playback, repeated play, same route, menu reset, playback after navigation.');
await run('location.hash="#generate";route();var skipPrevented=false;var contentFocused=false;$("content").focus=()=>{contentFocused=true};skipToContent({preventDefault(){skipPrevented=true}});if(!skipPrevented){location.hash="#content";route()}');
assert.equal(await run('skipPrevented'),true,'skip link must prevent hash navigation');
assert.equal(await run('location.hash'),'#generate','skip link must preserve selected screen URL');
assert.equal(await run('$("generate").hidden'),false,'skip link must preserve generator');
assert.equal(await run('$("dashboard").hidden'),true,'skip link must not open dashboard');
assert.equal(await run('contentFocused'),true,'skip link must focus main content');
// Bind the real filter/pagination listeners without running network startup or timers.
vm.runInContext(source.slice(source.indexOf('$("library-search").addEventListener'),source.indexOf('window.addEventListener("hashchange"')),context);
const template=readFileSync(resolve(__dirname,'../src/automusic/templates/web/index.html'),'utf8');
for(const id of ['jobs-size','library-size','favorites-only']) assert.match(template,new RegExp(`for="${id}"`));
for(const kind of ['jobs','library']) for(const suffix of ['size','previous','next','range']) assert.match(template,new RegExp(`id="${kind}-${suffix}"`));
await run('$("source-filter").value="all";$("library-search").value="";$("favorites-only").checked=false;libraryCategory=null;state.libraryError=null;state.librarySize=20;state.libraryPage=1;state.jobsSize=20;state.jobsPage=1;state.library=Array.from({length:45},(_,i)=>({id:`page-${i}`,title:`Song ${i}`,category_id:i<25?"lofi":"study",audio_url:`/api/library/page-${i}/audio`,favorite:i===2}));renderLibrary()');
const articles=()=>nodes.get('library-list').children.filter(n=>n.tagName==='article');
assert.equal(articles().length,20);
assert.equal(articles()[0].querySelector('[data-order]').textContent,'01');
assert.equal(articles()[19].querySelector('[data-order]').textContent,'20');
assert.equal(nodes.get('library-list').children.filter(n=>n.tagName==='h3').length,1);
const pagedAudio=articles()[0].querySelector('audio');pagedAudio.play();pagedAudio.currentTime=12;
await run('renderLibrary()');
assert.equal(articles()[0].querySelector('audio'),pagedAudio);
assert.equal(pagedAudio.pauseCalls,0);
nodes.get('library-next').dispatchEvent({type:'click'});
assert.equal(await run('state.libraryPage'),2);
assert.equal(articles().length,20);
assert.equal(articles()[0].querySelector('[data-order]').textContent,'21');
assert.equal(nodes.get('library-list').children.filter(n=>n.tagName==='h3').length,2);
assert.equal(pagedAudio.paused,true);
assert.equal(await run('playingAudio'),null);
nodes.get('library-size').value='50';nodes.get('library-size').dispatchEvent({type:'change'});
assert.equal(await run('state.libraryPage'),1);
assert.equal(articles().length,45);
assert.equal(articles()[0].querySelector('[data-order]').textContent,'01');
assert.equal(articles()[44].querySelector('[data-order]').textContent,'45');
assert.equal(await run('state.jobsSize'),20);
assert.equal(await run('state.jobsPage'),1);
nodes.get('library-size').value='30';nodes.get('library-size').dispatchEvent({type:'change'});
assert.equal(await run('state.librarySize'),20);
await run('state.libraryPage=3;selectLibraryCategory("study")');
assert.equal(await run('state.libraryPage'),1);
assert.equal(articles().length,20);
await run('libraryCategory=null;state.libraryPage=3;state.library=state.library.slice(0,21);renderLibrary()');
assert.equal(await run('state.libraryPage'),2);
assert.equal(articles().length,1);
await run('state.libraryPage=1;renderLibrary()');
const favoriteArticle=articles()[0];const favoriteAudio=favoriteArticle.querySelector('audio');const favoriteButton=favoriteArticle.querySelector('button');
favoriteAudio.play();
const favoriteId=favoriteArticle.dataset.id;
response=()=>({ok:true,json:async()=>({id:favoriteId,favorite:true})});
await run(`toggleFavorite(${JSON.stringify(favoriteId)},$("library-list").children.find(n=>n.dataset.id===${JSON.stringify(favoriteId)}).querySelector("button"))`);
assert.equal(articles()[0],favoriteArticle,'star toggle must preserve article and player');
assert.equal(favoriteAudio.paused,false);
assert.equal(favoriteButton.getAttribute('aria-pressed'),'true');
assert.equal(JSON.parse(requests.at(-1).options.body).favorite,true);
assert.equal(requests.at(-1).options.headers['X-CSRF-Token'],'token');
response=()=>{throw new Error('save offline');};
await run(`toggleFavorite(${JSON.stringify(favoriteId)},$("library-list").children.find(n=>n.dataset.id===${JSON.stringify(favoriteId)}).querySelector("button"))`);
assert.equal(favoriteButton.disabled,false);
assert.equal(favoriteButton.getAttribute('aria-pressed'),'true','failed save must not report success');
assert.match(nodes.get('favorite-message').textContent,/저장하지 못했습니다/);
await run('$("favorites-only").checked=true;resetLibraryPage()');
assert.equal(articles().every(n=>n.querySelector('button').getAttribute('aria-pressed')==='true'),true);
// A pending job outside the displayed page still drives pending/summary state.
await run('loadJobs=originalLoadJobs;state.pending={jobId:"outside"};state.jobsPage=1;state.jobStatuses=new Map()');
response=()=>({ok:true,json:async()=>({items:[...Array.from({length:20},(_,i)=>({id:`done-${i}`,status:'completed'})),{id:'outside',status:'failed',error:'outside failed'}]})});
await run('loadJobs()');
assert.equal(nodes.get('job-list').children.length,20);
assert.equal(await run('state.pending'),null);
assert.match(nodes.get('form-error').textContent,/outside failed/);
assert.match(nodes.get('jobs-message').textContent,/21개/);
nodes.get('jobs-next').dispatchEvent({type:'click'});
assert.equal(nodes.get('job-list').children[0].dataset.id,'outside');
// A stale GET cannot undo a later successful save.
await run('loadLibrary=originalLoadLibrary;$("favorites-only").checked=false;$("source-filter").value="all";state.libraryPage=1;renderLibrary()');
const staleItems=JSON.parse(await run('JSON.stringify(state.library)'));
let finishRead;
response=()=>new Promise(resolve=>{finishRead=resolve;});
const reading=run('loadLibrary()');
response=()=>({ok:true,json:async()=>({id:favoriteId,favorite:false})});
await run(`toggleFavorite(${JSON.stringify(favoriteId)},$("library-list").children.find(n=>n.dataset.id===${JSON.stringify(favoriteId)}).querySelector("button"))`);
finishRead({ok:true,json:async()=>({items:staleItems})});await reading;
assert.equal(await run(`state.library.find(n=>n.id===${JSON.stringify(favoriteId)}).favorite`),false);
// Recreating the button while a save is pending must retain the ID-level lock.
let finishSave;
response=()=>new Promise(resolve=>{finishSave=resolve;});
const saving=run(`toggleFavorite(${JSON.stringify(favoriteId)},$("library-list").children.find(n=>n.dataset.id===${JSON.stringify(favoriteId)}).querySelector("button"))`);
await run('renderRecords("library-list",[]);renderLibrary()');
const recreated=articles().find(n=>n.dataset.id===favoriteId).querySelector('button');
assert.equal(recreated.disabled,true);
const savingRequestCount=requests.length;
await run(`toggleFavorite(${JSON.stringify(favoriteId)},$("library-list").children.find(n=>n.dataset.id===${JSON.stringify(favoriteId)}).querySelector("button"))`);
assert.equal(requests.length,savingRequestCount);
finishSave({ok:true,json:async()=>({id:favoriteId,favorite:true})});await saving;
assert.equal(recreated.disabled,false);
assert.equal(recreated.getAttribute('aria-pressed'),'true');
for(const [id,event] of [['library-search','input'],['source-filter','change'],['favorites-only','change']]) {
 await run('state.libraryPage=2');nodes.get(id).dispatchEvent({type:event});
 assert.equal(await run('state.libraryPage'),1,`${id} must reset pagination through its real listener`);
}
console.log('Pagination/favorites passed: 20/50/100 boundaries, independent controls, clamp, grouping, audio retention/removal, save success/failure, CSRF, full pending-job tracking.');
console.log('Design regression groups passed: non-live timestamps, status changes, persistent library errors, recovery, model details, audio node reuse. Partial-failure recovery and 14 baseline behavior groups passed: URL boundaries, null metadata, ambiguous acceptance, duplicate click, immutable retry, CSRF, accepted job, cancel, scheduler unknown, locks');
})().catch(e=>{console.error(e);process.exitCode=1;});

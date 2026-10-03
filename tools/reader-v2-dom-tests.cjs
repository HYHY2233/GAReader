// Offline logic tests. Geometry, native dialogs and popup are mocked, not browser evidence.
const {JSDOM}=require('jsdom');
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const {webcrypto}=require('node:crypto');
const root=path.resolve(__dirname,'..'),checks=[],html=fs.readFileSync(path.join(root,'evidence/reader-tools-fixture.html'),'utf8');
const delay=ms=>new Promise(r=>setTimeout(r,ms));
async function fixture(){
 const dom=new JSDOM(html,{url:'https://reader.test/paper/',runScripts:'outside-only',pretendToBeVisual:true});
 const w=dom.window,d=w.document,queries=[],errors=[],calls=[];let blocked=false,fail=false;
 w.addEventListener('error',e=>{errors.push(e.error);e.preventDefault();});
 Object.defineProperty(w,'crypto',{value:webcrypto});w.TextEncoder=TextEncoder;
 w.HTMLDialogElement.prototype.showModal=function(){this.open=true;};
 w.HTMLDialogElement.prototype.close=function(){this.open=false;this.dispatchEvent(new w.Event('close'));};
 w.matchMedia=()=>({matches:false,addEventListener(){}});w.ResizeObserver=class{observe(){}};
 w.CSS={highlights:new Map()};w.Highlight=class{constructor(...ranges){this.ranges=ranges;}};
 w.scrollTo=()=>{};w.HTMLElement.prototype.scrollIntoView=function(){};w.confirm=()=>true;
 const rect={left:100,right:320,top:200,bottom:222,width:220,height:22};
 w.HTMLElement.prototype.getBoundingClientRect=()=>rect;
 w.HTMLElement.prototype.getClientRects=function(){const view=d.getElementById('reader')?.dataset.view;
  return this.closest('[hidden]')||view==='zh'&&this.closest('.en')||view==='en'&&this.closest('.zh')?[]:[rect];};
 w.Range.prototype.getClientRects=()=>[rect];w.Range.prototype.getBoundingClientRect=()=>rect;
 d.querySelector('.readerbar').getBoundingClientRect=()=>({top:0,bottom:70,height:70});
 w.fetch=async(url,options={})=>{assert.ok(url.startsWith('/api/papers/'));calls.push({url,options});
  if(options.method==='POST'){if(fail)throw Error('离线，未保存');return {ok:true,json:async()=>({id:7,version:1})};}
  return {ok:true,json:async()=>({threads:[],count:0,cursor:new Date().toISOString()})};};
 w.open=()=>{if(blocked)return null;const p={opener:w,closed:false,close(){},location:{replace(url){assert.equal(p.opener,null);queries.push(url);}}};return p;};
 for(const name of ['reader-text','reader-views','reader','reader-google','reader-annotations'])w.eval(fs.readFileSync(path.join(root,'app/static',name+'.js'),'utf8'));
 await delay(30);
 async function select(text){const p=d.querySelector('#p-p1 .en p');p.textContent=text;const r=d.createRange();r.selectNodeContents(p);
  w.getSelection().removeAllRanges();w.getSelection().addRange(r);d.dispatchEvent(new w.Event('selectionchange'));await delay(130);}
 return {w,d,errors,queries,calls,select,block:()=>blocked=true,fail:()=>fail=true,close:()=>w.close()};
}
async function check(name,fn){const f=await fixture();try{await fn(f);assert.equal(f.errors.length,0,f.errors.map(e=>e.message).join('; '));checks.push({name,status:'PASS'});}catch(e){checks.push({name,status:'FAIL',detail:e.message});}finally{f.close();}console.log(checks.at(-1));}
(async()=>{
 await check('Explicit Google click encodes full selection; refusal and oversized queries remain editable',async f=>{
  await f.select(' C++ & H₂ / 控制体? "模型"\n alpha beta ');assert.equal(f.d.getElementById('selection-tools').hidden,false);assert.equal(f.queries.length,0);
  f.d.getElementById('selection-google').click();assert.equal(new URL(f.queries[0]).searchParams.get('q'),'C++ & H₂ / 控制体? "模型" alpha beta');
  f.block();f.w.GAReaderGoogle.search('氨 synthesis');assert.equal(f.d.getElementById('google-dialog').open,true);
  assert.equal(new URL(f.d.getElementById('google-tab').href).searchParams.get('q'),'氨 synthesis');
  f.w.GAReaderGoogle.search('字'.repeat(2100));assert.equal(f.d.getElementById('google-query').value.length,2100);assert.equal(f.d.getElementById('google-tab').hidden,true);
 });
 await check('Numeric limits, slider, increment, reset and account preferences',async f=>{
  const size=f.d.getElementById('font-size');size.value='99';size.dispatchEvent(new f.w.Event('change'));assert.equal(f.w.GAReader.font,40);
  f.d.getElementById('font-down').click();assert.equal(f.w.GAReader.font,39);
  const slider=f.d.getElementById('font-range');slider.value='12';slider.dispatchEvent(new f.w.Event('input'));assert.equal(size.value,'12');
  f.d.getElementById('font-reset').click();assert.equal(f.w.GAReader.font,18);
  const theme=f.d.getElementById('theme');theme.value='dark';theme.dispatchEvent(new f.w.Event('change'));f.d.getElementById('inline-toggle').click();
  const stored=JSON.parse(f.w.localStorage.getItem(`gareader:preferences:v2:${f.d.getElementById('reader').dataset.user}`));
  assert.equal(stored.font,18);assert.equal(stored.theme,'dark');assert.equal(stored.inline,false);
 });
 await check('Codepoint ranges across inline tags, composed accents, Greek, subscripts, emoji and Hangul',async f=>{
  const p=f.d.querySelector('#p-p1 .en p');p.innerHTML='A 🐈 <em>cafe</em>\u0301 α H<sub>2</sub>O <sup>[2]</sup> 👩‍🔬 각';
  const map=f.w.GAReaderText.logical(p);assert.equal(map.text,'A 🐈 café α H2O [2] 👩‍🔬 각');
  const start=map.chars.indexOf('🐈'),end=map.chars.indexOf('O')+1,range=f.w.GAReaderText.restore(map,start,end),selected=f.w.GAReaderText.selected(range,map);
  assert.equal(selected.quote,'🐈 café α H2O');assert.equal(selected.start,start);assert.equal(selected.end,end);assert.equal(range.toString().normalize('NFC'),selected.quote);
 });
 await check('Continuous same-language segments; visible mixed languages rejected',async f=>{
  const start=f.d.querySelector('#p-h1 .en').firstChild,end=f.d.querySelector('#p-p1 .en p').firstChild;
  f.w.GAReader.setView('en');const range=f.d.createRange();range.setStart(start,1);range.setEnd(end,10);
  f.w.getSelection().removeAllRanges();f.w.getSelection().addRange(range);f.d.dispatchEvent(new f.w.Event('selectionchange'));await delay(130);
  assert.equal(f.w.GAReaderAnnotations.selection.source.segments.length,2);
  f.w.GAReader.setView('both');f.d.dispatchEvent(new f.w.Event('selectionchange'));await delay(130);assert.equal(f.d.getElementById('selection-tools').hidden,true);
 });
 await check('Draft retained after view switch, close and failed save; double submit sends once',async f=>{
  f.fail();await f.select('Complete English paragraph.');f.d.getElementById('selection-annotate').click();await delay(30);
  const input=f.d.getElementById('annotation-body');input.value='未提交的草稿';input.dispatchEvent(new f.w.Event('input'));
  f.w.GAReader.setView('zh');f.d.getElementById('annotations-close').click();f.d.getElementById('annotations-toggle').click();assert.equal(input.value,'未提交的草稿');
  const form=f.d.getElementById('annotation-form');form.dispatchEvent(new f.w.Event('submit',{cancelable:true}));form.dispatchEvent(new f.w.Event('submit',{cancelable:true}));await delay(30);
  assert.equal(f.calls.filter(c=>c.options.method==='POST').length,1);assert.match(f.d.getElementById('annotation-status').textContent,/未保存/);
  assert.equal(JSON.parse(f.w.localStorage.getItem(f.w.GAReaderAnnotations.editor.key)).body,'未提交的草稿');
 });
 await check('Search highlighting is independent of the annotation visibility preference',async f=>{
  const q=f.d.getElementById('in-paper-search');q.value='paragraph';q.dispatchEvent(new f.w.KeyboardEvent('keydown',{key:'Enter'}));
  assert.equal(f.w.CSS.highlights.get('search-results').ranges.length,1);f.w.GAReaderAnnotations.setInline(false);f.w.GAReaderAnnotations.paintGeometry();
  assert.equal(f.w.CSS.highlights.get('search-results').ranges.length,1);f.d.getElementById('annotations-toggle').click();assert.equal(f.w.GAReader.settings.inline,false);
 });
 fs.writeFileSync(path.join(root,'evidence/reader-dom-results.json'),JSON.stringify({kind:'offline DOM simulation; not visual/browser evidence',checks},null,2));
 if(checks.some(c=>c.status==='FAIL'))process.exitCode=1;
})().catch(e=>{console.error(e);process.exitCode=1;});

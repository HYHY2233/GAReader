// Offline DOM logic tests: no browser, localhost access, or network requests.
const {JSDOM}=require('jsdom');
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const root=path.resolve(__dirname,'..');
const html=fs.readFileSync(path.join(root,'evidence/reader-tools-fixture.html'),'utf8');
const readerScript=fs.readFileSync(path.join(root,'app/static/reader.js'),'utf8');
const googleScript=fs.readFileSync(path.join(root,'app/static/reader-google.js'),'utf8');
const checks=[];
const delay=ms=>new Promise(resolve=>setTimeout(resolve,ms));

async function fixture(){
 const dom=new JSDOM(html,{url:'https://reader.test/paper/',runScripts:'outside-only',pretendToBeVisual:true});
 const w=dom.window,d=w.document,opened=[],queries=[],scrolls=[],errors=[];let blocked=false,network=0;
 w.addEventListener('error',event=>{errors.push(event.error);event.preventDefault();});
 // jsdom does not implement native dialogs or layout; only their state transitions are simulated.
 w.HTMLDialogElement.prototype.showModal=function(){this.open=true;};
 w.HTMLDialogElement.prototype.close=function(){this.open=false;this.dispatchEvent(new w.Event('close'));};
 w.matchMedia=()=>({matches:false,addEventListener(){}});
 w.ResizeObserver=class{observe(){}};
 w.CSS={highlights:new Map()};w.Highlight=class{constructor(...ranges){this.ranges=ranges;}};
 w.scrollTo=(...args)=>scrolls.push(args);w.HTMLElement.prototype.scrollIntoView=function(){};
 w.fetch=()=>{network++;throw Error('Network is not allowed in this test');};
 Object.defineProperties(w,{innerWidth:{value:1440,writable:true},innerHeight:{value:960,writable:true}});
 Object.defineProperties(w.screen,{availWidth:{value:1440},availHeight:{value:1000}});
 d.querySelector('.readerbar').getBoundingClientRect=()=>({top:0,bottom:70,height:70});
 Object.defineProperties(d.getElementById('selection-google'),{offsetWidth:{value:130},offsetHeight:{value:34}});
 let rect={left:100,right:320,top:200,bottom:222,width:220,height:22};
 w.Range.prototype.getClientRects=()=>[rect];w.Range.prototype.getBoundingClientRect=()=>rect;
 w.open=(url,target,features)=>{
  opened.push({url,target,features});if(blocked)return null;
  const popup={opener:w,closed:false,close(){this.closed=true;},location:{replace(url){assert.equal(popup.opener,null);queries.push(url);}}};
  return popup;
 };
 w.eval(readerScript);w.eval(googleScript);await delay(20);scrolls.length=0;
 async function select(text,inside=true){
  const p=inside?d.querySelector('#article .paragraph .en p'):d.querySelector('.readerbar h1');
  p.textContent=text;const range=d.createRange();range.selectNodeContents(p);
  const selection=w.getSelection();selection.removeAllRanges();selection.addRange(range);
  d.dispatchEvent(new w.Event('selectionchange'));await delay(150);
 }
 return {w,d,opened,queries,scrolls,errors,select,network:()=>network,block:()=>{blocked=true;},rect:value=>{rect=value;},close:()=>w.close()};
}

async function check(name,fn){
 const f=await fixture();
 try{await fn(f);assert.equal(f.errors.length,0,f.errors.map(e=>e.message).join('; '));checks.push({name,status:'PASS'});console.log('PASS '+name);}
 catch(error){checks.push({name,status:'FAIL',detail:error.message});console.log('FAIL '+name+': '+error.message);}
 finally{f.close();}
}

(async()=>{
 await check('Selected paragraph opens encoded Google query only after click',async f=>{
  const selected='  C++ & H₂ / 控制体? "模型"\n alpha beta  ';
  await f.select(selected);
  assert.equal(f.d.getElementById('selection-google').hidden,false);
  assert.equal(f.opened.length,0);assert.equal(f.network(),0);
  f.d.getElementById('selection-google').click();
  assert.equal(f.opened.length,1);assert.equal(f.opened[0].url,'about:blank');
  assert.match(f.opened[0].features,/popup=yes/);
  const url=new URL(f.queries[0]);assert.equal(url.origin,'https://www.google.com');
  assert.equal(url.searchParams.get('q'),'C++ & H₂ / 控制体? "模型" alpha beta');
  assert.equal(f.scrolls.length,0);assert.equal(f.network(),0);
 });
 await check('Only article selection is offered; viewport placement is clamped',async f=>{
  await f.select('outside article',false);assert.equal(f.d.getElementById('selection-google').hidden,true);
  f.w.innerWidth=390;f.rect({left:350,right:389,top:905,bottom:930,width:39,height:25});
  await f.select('长段落 '.repeat(70));const button=f.d.getElementById('selection-google');
  assert.equal(button.hidden,false);assert.ok(parseFloat(button.style.left)+130<=390);
  assert.ok(parseFloat(button.style.top)+34<=960);
  f.w.dispatchEvent(new f.w.Event('scroll'));assert.equal(button.hidden,true);
  assert.equal(f.opened.length,0);
 });
 await check('Popup refusal offers an exact-query link in the editor',async f=>{
  f.block();await f.select('氨 synthesis & control');f.d.getElementById('selection-google').click();
  assert.equal(f.d.getElementById('google-dialog').open,true);
  assert.equal(f.d.getElementById('google-query').value,'氨 synthesis & control');
  const link=f.d.getElementById('google-tab');assert.equal(link.hidden,false);
  assert.equal(new URL(link.href).searchParams.get('q'),'氨 synthesis & control');
  assert.match(link.rel,/noopener/);assert.match(link.rel,/noreferrer/);
  assert.match(f.d.getElementById('google-status').textContent,/小窗口未能打开/);
  assert.equal(f.queries.length,0);assert.equal(f.scrolls.length,0);
 });
 await check('Manual query and keyboard shortcut do not search before submission',async f=>{
  f.d.getElementById('google-button').click();assert.equal(f.d.getElementById('google-dialog').open,true);
  assert.equal(f.opened.length,0);const query=f.d.getElementById('google-query');
  query.value='control volume';query.dispatchEvent(new f.w.Event('input'));
  f.d.getElementById('google-form').dispatchEvent(new f.w.Event('submit',{bubbles:true,cancelable:true}));
  assert.equal(new URL(f.queries[0]).searchParams.get('q'),'control volume');
  assert.equal(f.d.getElementById('google-dialog').open,false);
  f.d.dispatchEvent(new f.w.KeyboardEvent('keydown',{key:'g',altKey:true,bubbles:true}));
  assert.equal(f.d.getElementById('google-dialog').open,true);assert.equal(f.opened.length,1);
 });
 await check('Long selection is retained for editing, never silently truncated',async f=>{
  const text='字'.repeat(2100);await f.select(text);f.d.getElementById('selection-google').click();
  assert.equal(f.opened.length,0);assert.equal(f.d.getElementById('google-query').value,text);
  assert.equal(f.d.getElementById('google-tab').hidden,true);
  assert.match(f.d.getElementById('google-status').textContent,/2000/);
  const query=f.d.getElementById('google-query');query.value='short query';query.dispatchEvent(new f.w.Event('input'));
  assert.equal(f.d.getElementById('google-tab').hidden,false);
 });
 await check('Visible toolbar preferences apply and persist without opening a panel',async f=>{
  const theme=f.d.getElementById('theme'),size=f.d.getElementById('font-size'),sources=f.d.getElementById('source-toggle');
  for(const control of [theme,size,sources])assert.ok(control.closest('.readerbar'));
  theme.value='dark';theme.dispatchEvent(new f.w.Event('change'));assert.ok(f.d.documentElement.classList.contains('dark'));
  size.value='22';size.dispatchEvent(new f.w.Event('change'));assert.ok(f.d.body.classList.contains('font-22'));
  sources.checked=false;sources.dispatchEvent(new f.w.Event('change'));assert.ok(f.d.body.classList.contains('hide-sources'));
  const stored=JSON.parse(f.w.localStorage.getItem(f.w.localStorage.key(0)));
  assert.equal(stored.theme,'dark');assert.equal(stored.font,22);assert.equal(stored.sources,false);
  assert.equal(f.d.documentElement.style.getPropertyValue('--readerbar-height'),'70px');
  assert.equal(f.d.querySelector('dialog[open]'),null);assert.equal(f.network(),0);
 });
 await check('Contents, in-paper search and image dialog remain connected',async f=>{
  f.d.querySelector('[data-panel=contents]').click();assert.equal(f.d.getElementById('panel').open,true);
  f.d.querySelector('[data-close]').click();
  f.d.querySelector('[data-panel=search]').click();const query=f.d.getElementById('in-paper-search');
  query.value='paragraph';query.dispatchEvent(new f.w.KeyboardEvent('keydown',{key:'Enter',bubbles:true}));
  assert.match(f.d.getElementById('search-status').textContent,/第 1/);
  assert.equal(f.d.getElementById('panel').open,false);assert.equal(f.d.getElementById('image-dialog').open,false);
 });
 const result={kind:'offline DOM simulation; geometry, native dialog state and window.open mocked; not browser/Google loading verification',checks};
 fs.writeFileSync(path.join(root,'evidence/reader-dom-results.json'),JSON.stringify(result,null,2));
 if(checks.some(c=>c.status==='FAIL'))process.exitCode=1;
})().catch(error=>{console.error(error);process.exitCode=1;});

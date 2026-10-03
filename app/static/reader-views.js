'use strict';
(() => {
  const reader=document.getElementById('reader');if(!reader)return;
  const $=id=>document.getElementById(id),article=$('article');
  const key=`gareader:preferences:v2:${reader.dataset.user}`;
  const positionKey=`gareader:position:v2:${reader.dataset.user}:${reader.dataset.paper}:${reader.dataset.revision}`;
  let settings={},position={};
  try {settings=JSON.parse(localStorage.getItem(key)||'{}');position=JSON.parse(localStorage.getItem(positionKey)||'{}');}catch{}
  if(!Object.keys(settings).length)try{const old=JSON.parse(localStorage.getItem(`paper-reader:v1:${reader.dataset.user}:${reader.dataset.paper}:${reader.dataset.contentHash}`)||'{}');settings={font:old.font,theme:old.theme,sources:old.sources};}catch{}
  const system=matchMedia('(prefers-color-scheme: dark)');
  const manifest=JSON.parse($('representation-manifest')?.textContent||'null');
  let view='both',font=Math.round(Math.min(40,Math.max(12,Number(settings.font)||18))),viewEpoch=0;
  let readyResolve;const ready=new Promise(resolve=>{readyResolve=resolve;});
  const persist=()=>{try{localStorage.setItem(key,JSON.stringify(settings));}catch{}};
  const announce=message=>{const el=$('reader-status');el.textContent=message;};
  const notify=()=>document.dispatchEvent(new CustomEvent('gareader:layout'));
  function sizing(){
    for(const pair of article.querySelectorAll('.pair'))pair.classList.toggle('stacked-pair',view==='both'&&pair.getBoundingClientRect().width<2*Math.max(340,18*font)+32);
    notify();
  }
  function appearance(){
    const theme=settings.theme||'auto';
    document.documentElement.classList.toggle('dark',theme==='dark'||theme==='auto'&&system.matches);
    document.documentElement.classList.toggle('sepia',theme==='sepia');
    $('theme').value=theme;document.body.classList.toggle('hide-sources',settings.sources===false);
    document.documentElement.classList.toggle('reduce-motion',!!settings.reduceMotion);
    $('reduce-motion').checked=!!settings.reduceMotion;
    $('source-toggle').checked=settings.sources!==false;
    article.style.setProperty('--article-size',font+'px');
    $('font-size').value=font;$('font-range').value=font;
    $('font-down').disabled=font===12;$('font-up').disabled=font===40;
    settings.font=font;persist();requestAnimationFrame(sizing);
  }
  function setFont(value){
    const parsed=Number(value);if(!Number.isFinite(parsed)||value===''){announce('字号请输入 12—40 的整数。');$('font-size').value=font;return;}
    const next=Math.round(Math.min(40,Math.max(12,parsed)));
    if(next!==parsed)announce(`字号已限制为 ${next} px。`);else announce(`正文字号 ${next} px`);
    font=next;appearance();
  }
  function setView(next,{remember=true,restore=true}={}){
    if(window.GAReaderComposer?.composing){announce('请先完成正在输入的文字。');return;}
    const epoch=++viewEpoch;
    if(!['both','en','zh','pdf'].includes(next))return;
    if(next==='pdf'&&reader.dataset.hasPdf!=='true'){announce('未提供原版 PDF');return;}
    if(remember)savePosition();
    view=next;reader.dataset.view=view;
    article.hidden=view==='pdf';$('pdf-reader').hidden=view!=='pdf';$('pdf-controls').hidden=view!=='pdf';$('html-controls').hidden=view==='pdf';
    for(const button of document.querySelectorAll('button[data-view]')){button.classList.toggle('selected',button.dataset.view===view);button.setAttribute('aria-pressed',String(button.dataset.view===view));}
    $('view-label').textContent={both:'中英对照',en:'英文原文',zh:'中文译文',pdf:'原版 PDF'}[view];
    appearance();document.dispatchEvent(new CustomEvent('gareader:view',{detail:{view}}));
    if(restore&&position.unit_id&&!location.hash&&!new URLSearchParams(location.search).has('thread'))requestAnimationFrame(()=>{if(epoch===viewEpoch&&view!=='pdf')document.getElementById(position.unit_id)?.scrollIntoView({block:'start',behavior:'instant'});});
  }
  function savePosition(){
    if(view==='pdf'){position.pdf_page=window.GAReaderPDF?.currentPage()||0;}
    else {
      const top=document.querySelector('.readerbar').getBoundingClientRect().bottom+10;
      const units=[...article.querySelectorAll('[data-unit]')].filter(u=>u.getClientRects().length);
      const unit=units.find(u=>u.getBoundingClientRect().bottom>top);
      if(unit)position.unit_id=unit.dataset.unit;
    }
    position.view=view;
    try{localStorage.setItem(positionKey,JSON.stringify(position));}catch{}
  }
  function capturePosition(){
    if(view==='pdf')return {view,pdf:window.GAReaderPDF?.capturePosition()};
    const top=document.querySelector('.readerbar').getBoundingClientRect().bottom+12;
    const candidates=[...article.querySelectorAll('[data-unit]')].map(el=>({el,rect:el.getBoundingClientRect()})).filter(x=>x.el.getClientRects().length&&x.rect.bottom>top);
    const unit=candidates.filter(x=>x.rect.top<=top).sort((a,b)=>a.rect.height-b.rect.height)[0]||candidates[0];
    return {view,unit_id:unit?.el.dataset.unit,offset:unit?unit.rect.top-top:0};
  }
  async function restorePosition(saved,{isCurrent=()=>true}={}){
    if(!saved||!isCurrent())return;
    if(view!==saved.view)setView(saved.view,{restore:false,remember:false});
    if(saved.view==='pdf'){await window.GAReaderPDF?.restorePosition(saved.pdf,{isCurrent});return;}
    await new Promise(resolve=>requestAnimationFrame(resolve));if(!isCurrent())return;
    const el=document.getElementById(saved.unit_id);if(!el)return;
    let details=el.closest('details');while(details){details.open=true;details=details.parentElement.closest('details');}
    const top=document.querySelector('.readerbar').getBoundingClientRect().bottom+12;
    window.scrollTo({top:scrollY+el.getBoundingClientRect().top-top-(saved.offset||0),behavior:'instant'});notify();
  }
  const core={reader,article,manifest,settings,position,announce,persist,setView,setFont,sizing,ready,capturePosition,restorePosition,
    get view(){return view;},get font(){return font;},emitLayout:notify};
  window.GAReader=core;
  $('font-down').addEventListener('click',()=>setFont(font-1));$('font-up').addEventListener('click',()=>setFont(font+1));
  $('font-size').addEventListener('change',e=>setFont(e.target.value));$('font-range').addEventListener('input',e=>setFont(e.target.value));
  $('font-size').addEventListener('keydown',e=>{if(e.key==='Enter'){e.preventDefault();setFont(e.target.value);}});
  $('font-reset').addEventListener('click',()=>setFont(18));
  $('theme').addEventListener('change',e=>{settings.theme=e.target.value;appearance();});
  $('reduce-motion').addEventListener('change',e=>{settings.reduceMotion=e.target.checked;appearance();});
  $('source-toggle').addEventListener('change',e=>{settings.sources=e.target.checked;appearance();});system.addEventListener('change',appearance);
  document.querySelectorAll('button[data-view]').forEach(b=>b.addEventListener('click',()=>setView(b.dataset.view)));
  let timer;window.addEventListener('scroll',()=>{clearTimeout(timer);timer=setTimeout(savePosition,400);},{passive:true});
  window.addEventListener('pagehide',savePosition);window.addEventListener('resize',()=>requestAnimationFrame(sizing));
  if(window.ResizeObserver)new ResizeObserver(()=>requestAnimationFrame(sizing)).observe(article);
  appearance();
  window.addEventListener('load',()=>{
    setView(new URLSearchParams(location.search).get('view')||position.view||'both',{remember:false});
    readyResolve();
    if(location.hash&&location.hash!=='#comments'&&location.hash!=='#annotations')setTimeout(()=>document.getElementById(decodeURIComponent(location.hash.slice(1)))?.scrollIntoView(),100);
  });
})();

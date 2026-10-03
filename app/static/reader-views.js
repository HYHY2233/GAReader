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
  let view='both',font=Math.round(Math.min(40,Math.max(12,Number(settings.font)||18))),restoreTimer;
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
  function setView(next,{remember=true}={}){
    if(!['both','en','zh','pdf'].includes(next))return;
    if(next==='pdf'&&reader.dataset.hasPdf!=='true'){announce('未提供原版 PDF');return;}
    if(remember)savePosition();
    view=next;reader.dataset.view=view;
    article.hidden=view==='pdf';$('pdf-reader').hidden=view!=='pdf';$('pdf-controls').hidden=view!=='pdf';$('html-controls').hidden=view==='pdf';
    for(const button of document.querySelectorAll('button[data-view]')){button.classList.toggle('selected',button.dataset.view===view);button.setAttribute('aria-pressed',String(button.dataset.view===view));}
    $('view-label').textContent={both:'中英对照',en:'英文原文',zh:'中文译文',pdf:'原版 PDF'}[view];
    appearance();document.dispatchEvent(new CustomEvent('gareader:view',{detail:{view}}));
    if(view!=='pdf'&&position.unit_id&&!location.hash){clearTimeout(restoreTimer);restoreTimer=setTimeout(()=>document.getElementById(position.unit_id)?.scrollIntoView({block:'start'}),70);}
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
  const core={reader,article,manifest,settings,position,announce,persist,setView,setFont,sizing,
    get view(){return view;},get font(){return font;},emitLayout:notify};
  window.GAReader=core;
  $('font-down').addEventListener('click',()=>setFont(font-1));$('font-up').addEventListener('click',()=>setFont(font+1));
  $('font-size').addEventListener('change',e=>setFont(e.target.value));$('font-range').addEventListener('input',e=>setFont(e.target.value));
  $('font-size').addEventListener('keydown',e=>{if(e.key==='Enter'){e.preventDefault();setFont(e.target.value);}});
  $('font-reset').addEventListener('click',()=>setFont(18));
  $('theme').addEventListener('change',e=>{settings.theme=e.target.value;appearance();});
  $('source-toggle').addEventListener('change',e=>{settings.sources=e.target.checked;appearance();});system.addEventListener('change',appearance);
  document.querySelectorAll('button[data-view]').forEach(b=>b.addEventListener('click',()=>setView(b.dataset.view)));
  let timer;window.addEventListener('scroll',()=>{clearTimeout(timer);timer=setTimeout(savePosition,400);},{passive:true});
  window.addEventListener('pagehide',savePosition);window.addEventListener('resize',()=>requestAnimationFrame(sizing));
  if(window.ResizeObserver)new ResizeObserver(()=>requestAnimationFrame(sizing)).observe(article);
  appearance();
  window.addEventListener('load',()=>{
    setView(new URLSearchParams(location.search).get('view')||position.view||'both',{remember:false});
    if(location.hash&&location.hash!=='#comments')setTimeout(()=>document.getElementById(decodeURIComponent(location.hash.slice(1)))?.scrollIntoView(),100);
  });
})();

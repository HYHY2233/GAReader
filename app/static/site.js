'use strict';
(() => {
 const user=document.body.dataset.readerUser,instance=document.body.dataset.readerInstance,key=`gareader:preferences:v2:${user}`;let preferences={};
 try{preferences=JSON.parse(localStorage.getItem(key)||'{}');}catch{}
 const system=matchMedia('(prefers-color-scheme: dark)'),picker=document.getElementById('site-theme'),motion=document.getElementById('reduce-motion');
 const persist=()=>{try{const latest=JSON.parse(localStorage.getItem(key)||'{}');localStorage.setItem(key,JSON.stringify({...latest,theme:preferences.theme||'auto',reduceMotion:!!preferences.reduceMotion}));}catch{}};
 const apply=()=>{if(document.getElementById('reader'))return;const theme=preferences.theme||'auto';document.documentElement.classList.toggle('dark',theme==='dark'||theme==='auto'&&system.matches);document.documentElement.classList.toggle('sepia',theme==='sepia');document.documentElement.classList.toggle('reduce-motion',!!preferences.reduceMotion);if(picker)picker.value=theme;if(motion)motion.checked=!!preferences.reduceMotion;};
 apply();system.addEventListener('change',apply);
 picker?.addEventListener('change',()=>{preferences.theme=picker.value;persist();apply();});
 if(!document.getElementById('reader'))motion?.addEventListener('change',()=>{preferences.reduceMotion=motion.checked;persist();apply();});
 const prefix=`gareader:home:v3:${instance}:${user}:`,home=document.getElementById('library-home');
 if(home){
   const url=location.pathname+location.search,slot=prefix+url;
   const remember=()=>{try{sessionStorage.setItem(slot,String(scrollY));sessionStorage.setItem(prefix+'last',url);}catch{}};
   document.addEventListener('click',e=>{if(e.target.closest('a'))remember();});window.addEventListener('pagehide',remember);
   window.addEventListener('load',()=>{try{if(!location.hash)window.scrollTo(0,Number(sessionStorage.getItem(slot)||0));}catch{}});
   const links=[...document.querySelectorAll('.section-nav a[href^="#"]')];
   if(window.IntersectionObserver){const sections=[...document.querySelectorAll('.home-section')];const visible=new Set();     const observer=new IntersectionObserver(entries=>{entries.forEach(e=>e.isIntersecting?visible.add(e.target):visible.delete(e.target));const first=sections.find(s=>visible.has(s));if(first)links.forEach(a=>{if(a.hash==='#'+first.id)a.setAttribute('aria-current','location');else a.removeAttribute('aria-current');});},{rootMargin:'-70px 0px -45% 0px'});sections.forEach(s=>observer.observe(s));}
 }else{try{const url=sessionStorage.getItem(prefix+'last');if(url&&/^\/(?:\?[^#]*)?$/.test(url)){const back=document.querySelector('.reader-heading .back');if(back)back.href=url;}}catch{}}
 for(const select of document.querySelectorAll('[data-tag-select]')){
   const host=select.closest('.tag-field'),search=document.createElement('input'),chosen=document.createElement('div'),results=document.createElement('div'),status=document.createElement('p');
   search.type='search';search.placeholder='输入标签名筛选…';search.setAttribute('aria-label','筛选可选标签');search.autocomplete='off';chosen.className='tag-chosen';results.className='tag-results';status.className='muted';status.setAttribute('role','status');select.hidden=true;select.required=false;host.append(chosen,search,results,status);
   const render=()=>{const options=[...select.options],selected=options.filter(o=>o.selected);chosen.replaceChildren();for(const option of selected){const b=document.createElement('button');b.type='button';b.textContent=option.text+' ×';b.setAttribute('aria-label','移除标签 '+option.text);b.onclick=()=>{option.selected=false;render();};chosen.append(b);}results.replaceChildren();const matches=options.filter(o=>!o.selected&&o.text.toLocaleLowerCase().includes(search.value.trim().toLocaleLowerCase()));for(const option of matches.slice(0,12)){const b=document.createElement('button');b.type='button';b.textContent=option.text;b.disabled=selected.length>=5;b.onclick=()=>{option.selected=true;render();search.focus();};results.append(b);}status.textContent=`已选 ${selected.length} / 5`+(matches.length>12?' · 继续输入以缩小候选范围':'');search.setCustomValidity(selected.length<1?'请至少选择1个标签。':selected.length>5?'最多选择5个标签。':'');};search.addEventListener('input',render);render();
 }
})();
window.notify=function(text,error=false){const n=document.getElementById('toast');n.textContent=text;n.classList.toggle('error',error);n.classList.add('visible');clearTimeout(window.toastTimer);window.toastTimer=setTimeout(()=>n.classList.remove('visible'),5000);};

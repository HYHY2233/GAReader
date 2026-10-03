'use strict';
(() => {
 const article=document.getElementById('article');if(!article)return;
 const $=id=>document.getElementById(id);
 const button=$('selection-google'),dialog=$('google-dialog'),query=$('google-query'),tab=$('google-tab'),status=$('google-status');
 const limit=2000;let selectionText='',selectionTimer,origin=null;
 const clean=text=>text.replace(/\s+/g,' ').trim();
 const googleURL=text=>'https://www.google.com/search?q='+encodeURIComponent(text);
 function selected(){
  const selection=window.getSelection();
  if(!selection||selection.isCollapsed||selection.rangeCount!==1)return null;
  const range=selection.getRangeAt(0);
  if(!article.contains(range.startContainer)||!article.contains(range.endContainer))return null;
  const text=clean(selection.toString());if(!text)return null;
  const top=document.querySelector('.readerbar').getBoundingClientRect().bottom;
  const rectangles=[...range.getClientRects()].filter(r=>r.width>0&&r.height>0&&r.bottom>top&&r.top<innerHeight&&r.right>0&&r.left<innerWidth);
  return {text,rect:rectangles.at(-1)||range.getBoundingClientRect(),toolbarBottom:top};
 }
 function updateButton(){
  if(document.querySelector('dialog[open]')){button.hidden=true;return;}
  const selection=selected();
  if(!selection||selection.rect.bottom<=selection.toolbarBottom||selection.rect.top>=innerHeight||selection.rect.right<=0||selection.rect.left>=innerWidth){button.hidden=true;return;}
  selectionText=selection.text;button.hidden=false;
  const {rect,toolbarBottom}=selection,w=button.offsetWidth,h=button.offsetHeight;
  button.style.left=Math.max(8,Math.min(innerWidth-w-8,rect.left))+'px';
  const below=rect.bottom+8,above=rect.top-h-8;
  button.style.top=Math.max(toolbarBottom+8,Math.min(innerHeight-h-8,below+h+8<=innerHeight?below:above))+'px';
 }
 function updateLink(){
  const text=clean(query.value);tab.hidden=!text||text.length>limit;
  if(!tab.hidden)tab.href=googleURL(text);else tab.removeAttribute('href');
  query.setCustomValidity(text.length>limit?'请将检索内容缩短到 2000 字以内。':'');
  status.hidden=true;
 }
 function openEditor(text='',message=''){
  document.querySelectorAll('dialog[open]').forEach(d=>{if(d!==dialog)d.close();});
  button.hidden=true;origin=$('google-button');
  if(text)query.value=text;
  updateLink();if(!dialog.open)dialog.showModal();
  if(message){status.textContent=message;status.hidden=false;}
  query.focus();
 }
 function search(text){
  text=clean(text);if(!text)return;
  if(text.length>limit){openEditor(text,'选中内容较长，请缩短到 2000 字以内再检索。');return;}
  query.value=text;updateLink();button.hidden=true;
  const width=Math.min(700,Math.max(320,screen.availWidth-40));
  const height=Math.min(820,Math.max(400,screen.availHeight-80));
  const left=Math.max(0,Math.round(window.screenX+innerWidth-width-20)),top=Math.max(0,Math.round(window.screenY+40));
  let popup;
  try{
   // Keep this synchronous with the click. Disconnect the opener before navigating.
   popup=window.open('about:blank','_blank',`popup=yes,width=${width},height=${height},left=${left},top=${top},resizable=yes,scrollbars=yes`);
   if(!popup)throw Error('Popup unavailable');
   popup.opener=null;popup.location.replace(googleURL(text));
   if(dialog.open)dialog.close();
  }catch{
   if(popup)try{popup.close();}catch{}
   openEditor(text,'小窗口未能打开，可点击“新标签页打开”。');
  }
 }
 document.addEventListener('selectionchange',()=>{clearTimeout(selectionTimer);selectionTimer=setTimeout(updateButton,120);});
 document.addEventListener('pointerup',e=>{if(article.contains(e.target)){clearTimeout(selectionTimer);selectionTimer=setTimeout(updateButton,30);}});
 button.addEventListener('pointerdown',e=>e.preventDefault());
 button.addEventListener('click',()=>search(selectionText));
 $('google-button').addEventListener('pointerdown',e=>e.preventDefault());
 $('google-button').addEventListener('click',()=>openEditor(selected()?.text));
 $('google-close').addEventListener('click',()=>dialog.close());
 dialog.addEventListener('close',()=>origin?.focus({preventScroll:true}));
 dialog.addEventListener('click',e=>{const r=dialog.getBoundingClientRect();if(e.target===dialog&&(e.clientX<r.left||e.clientX>r.right||e.clientY<r.top||e.clientY>r.bottom))dialog.close();});
 query.addEventListener('input',updateLink);
 $('google-form').addEventListener('submit',e=>{e.preventDefault();search(query.value);});
 tab.addEventListener('click',()=>dialog.close());
 window.addEventListener('scroll',()=>{button.hidden=true;},{passive:true});
 window.addEventListener('resize',()=>{button.hidden=true;});
 document.addEventListener('keydown',e=>{
  if(e.key==='Escape')button.hidden=true;
  if(e.altKey&&!e.ctrlKey&&!e.metaKey&&e.key.toLowerCase()==='g'){e.preventDefault();openEditor(selected()?.text);}
 });
})();

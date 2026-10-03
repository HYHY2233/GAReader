'use strict';
(() => {
  const core=window.GAReader;if(!core)return;
  const $=id=>document.getElementById(id),dialog=$('google-dialog'),query=$('google-query'),tab=$('google-tab'),status=$('google-status');
  const clean=text=>String(text||'').replace(/\s+/g,' ').trim(),url=text=>'https://www.google.com/search?q='+encodeURIComponent(text);
  function updateLink(){const text=clean(query.value);tab.hidden=!text||[...text].length>2000;if(!tab.hidden)tab.href=url(text);else tab.removeAttribute('href');query.setCustomValidity([...text].length>2000?'请将检索内容缩短到 2000 字以内。':'');status.hidden=true;}
  function openEditor(text='',message=''){
    document.querySelectorAll('dialog[open]').forEach(d=>{if(d!==dialog)d.close();});$('selection-tools').hidden=true;
    if(text)query.value=text;updateLink();if(!dialog.open)dialog.showModal();
    if(message){status.textContent=message;status.hidden=false;}query.focus();
  }
  function search(text){
    text=clean(text);if(!text)return;if([...text].length>2000){openEditor(text,'选中内容较长，请精简后再检索。');return;}
    query.value=text;updateLink();$('selection-tools').hidden=true;
    const width=Math.min(700,Math.max(320,screen.availWidth-40)),height=Math.min(820,Math.max(400,screen.availHeight-80));
    let popup;
    try{popup=window.open('about:blank','_blank',`popup=yes,width=${width},height=${height},resizable=yes,scrollbars=yes`);if(!popup)throw Error();popup.opener=null;popup.location.replace(url(text));if(dialog.open)dialog.close();}
    catch{if(popup)try{popup.close();}catch{}openEditor(text,'小窗口未能打开，可点击“新标签页打开”。');}
  }
  $('google-button').addEventListener('pointerdown',e=>e.preventDefault());
  $('google-button').addEventListener('click',()=>openEditor(window.GAReaderAnnotations?.selection?.text||''));
  $('google-close').addEventListener('click',()=>dialog.close());dialog.addEventListener('close',()=>$('google-button').focus({preventScroll:true}));
  query.addEventListener('input',updateLink);$('google-form').addEventListener('submit',e=>{e.preventDefault();search(query.value);});tab.addEventListener('click',()=>dialog.close());
  document.addEventListener('keydown',e=>{if(e.altKey&&!e.ctrlKey&&!e.metaKey&&e.key.toLowerCase()==='g'){e.preventDefault();openEditor(window.GAReaderAnnotations?.selection?.text||'');}});
  window.GAReaderGoogle={search,openEditor};
})();

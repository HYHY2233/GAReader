'use strict';
(() => {
  const core=window.GAReader;if(!core)return;
  const reader=core.reader,back=document.getElementById('source-return');
  const prefix=`gareader:navigation:v3:${document.body.dataset.readerInstance}:${reader.dataset.user}:`;
  let generation=0,controller=null,callbacks={},returnTo=history.state?.gaReturn||null,busy=false;
  const cleanURL=value=>{const u=new URL(value,location.origin);if(u.origin!==location.origin||!/^\/papers\/[0-9a-f-]+\/(?:revisions\/[0-9a-f-]+\/)?$/.test(u.pathname))throw Error('来源地址不属于站内论文。');return u;};
  function capture(){return {url:location.href,paper:reader.dataset.paper,revision:reader.dataset.revision,
    position:core.capturePosition(),thread:callbacks.active?.()||null,inline:core.settings.inline!==false};}
  function cancel(){generation++;controller?.abort();controller=null;busy=false;}
  const guard=()=>{const value=generation;return ()=>value===generation;};
  function remember(record){history.replaceState({...history.state,gaPosition:record,gaReturn:returnTo},'',location.href);}
  async function source(note,index=0){
    if(window.GAReaderComposer?.composing)return;
    if(!note.source||!note.source_url)throw Error('批注来源已不可访问。');
    const url=cleanURL(note.source_url);
    const expected=`/papers/${reader.dataset.paper}/revisions/${note.source.revision_id}/`;
    if(url.pathname!==expected)throw Error('来源论文或修订不匹配。');
    if(!Number.isInteger(index)||index<0||index>=note.source.segments.length)throw Error('来源片段无效。');
    url.searchParams.set('segment',String(index));
    const origin=capture();cancel();const current=guard();controller=new AbortController();busy=true;
    window.GAReaderComposer?.save();
    try{
      const response=await fetch(url.href,{credentials:'same-origin',signal:controller.signal});
      if(!response.ok||response.redirected)throw Error('来源已不可访问，请检查登录状态、权限和内容修订。');
      await response.body?.cancel();if(!current())return;
      remember(origin);returnTo=returnTo||origin;
      if(note.source.revision_id!==reader.dataset.revision){
        sessionStorage.setItem(prefix+'pending',JSON.stringify({target:url.href,origin:returnTo,time:Date.now()}));
        location.assign(url.href);return;
      }
      history.pushState({gaReturn:returnTo},'',url.href);back.hidden=false;
      core.setView(note.source.created_view,{restore:false});const ready=guard();busy=true;
      const located=await callbacks.source?.(note.id,index,ready);
      if(ready()){remember(capture());busy=false;if(located)core.announce('已定位到批注来源。');}
    }catch(error){if(error.name!=='AbortError'){busy=false;core.announce(error instanceof TypeError?'无法连接来源，草稿仍保留，请恢复连接后重试。':error.message||'来源加载失败，草稿仍保留。');}}
  }
  async function restore(record){
    const url=cleanURL(record.url);cancel();window.GAReaderComposer?.save();
    if(record.paper!==reader.dataset.paper||record.revision!==reader.dataset.revision){
      sessionStorage.setItem(prefix+'restore',JSON.stringify({target:url.href,record,time:Date.now()}));location.assign(url.href);return;
    }
    history.pushState({gaPosition:record},'',url.href);returnTo=null;back.hidden=true;
    core.setView(record.position.view,{restore:false});const current=guard();busy=true;
    await callbacks.restore?.(record.thread,record.inline);
    await new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)));
    await core.restorePosition(record.position,{isCurrent:current});
    if(current()){busy=false;core.announce('已返回刚才的阅读位置。');}
  }
  back.addEventListener('click',()=>{if(returnTo&&!window.GAReaderComposer?.composing)restore(returnTo).catch(e=>core.announce(e.message));});
  document.addEventListener('gareader:view',cancel);
  window.addEventListener('pagehide',()=>{try{remember(capture());}catch{}});
  window.addEventListener('popstate',async()=>{
    cancel();returnTo=history.state?.gaReturn||null;back.hidden=!returnTo;
    const record=history.state?.gaPosition;
    if(record?.revision===reader.dataset.revision){core.setView(record.position.view,{restore:false});const current=guard();await callbacks.restore?.(record.thread,record.inline);await new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)));if(current())await core.restorePosition(record.position,{isCurrent:current});}
    else if(new URLSearchParams(location.search).has('thread'))await activateURL();
  });
  async function activateURL(){
    const params=new URLSearchParams(location.search),thread=Number(params.get('thread')),index=Number(params.get('segment')||0);
    if(Number.isInteger(thread)&&thread>0&&Number.isInteger(index)&&index>=0){
      core.setView(params.get('view')||core.view,{restore:false});const current=guard();
      await callbacks.source?.(thread,index,current);
    }
  }
  async function start(value){
    callbacks=value;
    for(const key of ['pending','restore'])try{
      const stored=JSON.parse(sessionStorage.getItem(prefix+key)||'null');
      if(stored){sessionStorage.removeItem(prefix+key);if(stored.target===location.href&&Date.now()-stored.time<120000){
        if(key==='pending')returnTo=stored.origin;
        else {core.setView(stored.record.position.view,{restore:false});const current=guard();await callbacks.restore?.(stored.record.thread,stored.record.inline);await new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)));if(current())await core.restorePosition(stored.record.position,{isCurrent:current});return;}
      }}
    }catch{}
    back.hidden=!returnTo;history.replaceState({...history.state,gaReturn:returnTo},'',location.href);
    if(history.state?.gaPosition){const record=history.state.gaPosition;core.setView(record.position.view,{restore:false});const current=guard();await callbacks.restore?.(record.thread,record.inline);await new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)));if(current())await core.restorePosition(record.position,{isCurrent:current});}
    else await activateURL();
  }
  window.GAReaderNavigation={source,capture,guard,cancel,start,get busy(){return busy;}};
})();

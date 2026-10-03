'use strict';
(() => {
  const core = window.GAReader;
  if (!core?.manifest) return;
  const $ = id => document.getElementById(id);
  const host = $('annotation-composer'), body = $('annotation-body'), status = $('annotation-status');
  let editor = null, busy = false, composing = false, callbacks = {}, opener = null;
  const instance = document.body.dataset.readerInstance || 'test';
  let tab;
  try {
    tab = sessionStorage.getItem('gareader:tab:v3') || crypto.randomUUID();
    sessionStorage.setItem('gareader:tab:v3',tab);
  } catch { tab = crypto.randomUUID(); }
  const changed = () => { callbacks.changed?.(); document.dispatchEvent(new Event('gareader:composer')); };
  let base, pointer;
  function restoreDraft(){
    base=`gareader:draft:v3:${instance}:${core.reader.dataset.user}:${core.reader.dataset.paper}:${tab}:`;pointer=base+'last';
    try{sessionStorage.setItem('gareader:tab:v3',tab);const key=localStorage.getItem(pointer),draft=JSON.parse(localStorage.getItem(key)||'null');
      if(key?.startsWith(base)&&draft?.key===key){editor=draft;body.value=draft.body||'';}}
    catch{} changed();
  }
  // A duplicated tab can inherit sessionStorage. A live-tab lease prevents it from overwriting its opener's draft.
  const tabReady=new Promise(resolve=>{
    if(!navigator.locks){restoreDraft();resolve();return;}
    const acquire=()=>navigator.locks.request(`gareader:tab:${instance}:${tab}`,{ifAvailable:true},async lock=>{
      if(!lock){tab=crypto.randomUUID();return acquire();}
      restoreDraft();resolve();await new Promise(release=>window.addEventListener('pagehide',release,{once:true}));
    }).catch(()=>{restoreDraft();resolve();});
    acquire();
  });
  function save() {
    if (!editor) return;
    editor.body = body.value;
    try { localStorage.setItem(editor.key,JSON.stringify(editor)); localStorage.setItem(pointer,editor.key); }
    catch { status.textContent = '浏览器无法保存草稿，请在离开前复制正文。'; }
  }
  function rememberFocus() { opener = document.activeElement; }
  function close() {
    if (busy || composing) return;
    save(); host.hidden = true; changed();
    if (opener?.isConnected) opener.focus({preventScroll:true});
    if (editor?.body) core.announce('草稿已收起并保留，可点击“继续草稿”。');
  }
  function sourceDisplay(source) {
    const root = $('composer-objects'); root.replaceChildren();
    if (!source) { root.textContent = '原来源已不可访问；正文草稿保留，可复制。'; return; }
    source.segments.forEach((segment,index) => {
      const quote = core.node('blockquote',GAAnnotationPresentation.objectLabel(segment,index,source.segments.length));
      root.append(quote);
    });
  }
  function show() {
    callbacks.beforeOpen?.(); host.hidden = false;
    $('annotation-editor-title').textContent = {new:'新建批注',reply:'回复这条批注',edit:'编辑自己的批注'}[editor.mode];
    $('annotation-save').textContent = {new:'保存批注',reply:'发表回复',edit:'保存修改'}[editor.mode];
    $('annotation-save').disabled = !!editor.unavailable;
    $('annotation-editor-source').textContent = GAAnnotationPresentation.sourceName(editor.source);
    body.value = editor.body || ''; sourceDisplay(editor.source);
    $('annotation-conflict').hidden = true; status.textContent = '';
    $('conflict-review').hidden=true;$('discard-confirm').hidden=true;
    changed(); body.focus({preventScroll:true});
  }
  async function open({mode='new',source=null,item=null,thread=null}={}) {
    await tabReady;
    if (busy || composing) return;
    save(); rememberFocus();
    source = source || thread?.source;
    const identity = JSON.stringify([source?.revision_id,mode,mode==='new'?source:item?.id]);
    const hash = [...new Uint8Array(await crypto.subtle.digest('SHA-256',new TextEncoder().encode(identity)))].map(n=>n.toString(16).padStart(2,'0')).join('');
    const key = base + hash;
    let old; try { old = JSON.parse(localStorage.getItem(key) || 'null'); } catch {}
    editor = old?.key === key ? old : {key,mode,source,thread:thread?.id || null,item:item?.id || null,
      version:item?.version,body:mode==='edit'?item.body:'',request_key:crypto.randomUUID(),signature:''};
    show(); save();
  }
  function revoke(threadId) {
    if (!editor || editor.thread !== threadId) return;
    editor.unavailable = true; editor.source = null; sourceDisplay(null); save();
    status.textContent = '这条讨论已删除、隐藏或不可访问。你的正文草稿保留，可复制后另建。';
    $('annotation-save').disabled = true;
  }
  async function submit(event) {
    event.preventDefault();
    if (!editor || busy || composing || event.isComposing || editor.unavailable || !body.value.trim()) return;
    save(); busy = true; $('annotation-save').disabled = true; status.textContent = '正在保存…';
    const current = editor, submitted = {...editor,body:body.value.trim()};
    try {
      let result;
      if (submitted.mode === 'edit') result = await core.api(`comments/${submitted.item}/`,'PATCH',{body:submitted.body,version:submitted.version});
      else {
        const signature = JSON.stringify([submitted.body,submitted.source,submitted.thread]);
        if (current.signature !== signature) { current.signature = signature; current.request_key = crypto.randomUUID(); save(); }
        result = submitted.mode === 'new'
          ? await core.api('annotations/','POST',{body:submitted.body,source:submitted.source,request_key:current.request_key})
          : await core.api('comments/','POST',{body:submitted.body,parent:submitted.thread,request_key:current.request_key});
      }
      try {
        localStorage.removeItem(current.key);
        if (localStorage.getItem(pointer) === current.key) localStorage.removeItem(pointer);
      } catch {}
      editor = null; body.value = ''; host.hidden = true; busy=false;
      changed();
      await callbacks.saved?.(submitted.mode === 'new' ? result.id : submitted.thread);
    } catch (error) {
      status.textContent = error.network ? '连接中断，未确认保存；草稿已保留，可安全重试。' : error.message || '连接失败，未确认保存；草稿已保留，可安全重试。';
      $('annotation-conflict').hidden = !(error.status === 409 && editor?.mode === 'edit'); save();
    } finally { busy = false; $('annotation-save').disabled = !!editor?.unavailable; }
  }
  $('annotation-form').addEventListener('submit',submit);
  body.addEventListener('input',save);
  body.addEventListener('keydown',event=>{if(event.ctrlKey&&event.key==='Enter'&&!event.isComposing&&!composing){event.preventDefault();$('annotation-form').requestSubmit();}});
  body.addEventListener('compositionstart',()=>{composing=true;});
  body.addEventListener('compositionend',()=>{composing=false;save();});
  $('annotation-cancel').addEventListener('click',close);
  $('composer-close').addEventListener('click',close);
  $('continue-draft').addEventListener('click',async()=>{if(editor){
    if(editor.thread){const latest=await callbacks.latest?.(editor.thread,editor.item);if(!latest?.source)revoke(editor.thread);}
    rememberFocus();show();
  }});
  $('annotation-discard').addEventListener('click',()=>{if(!busy&&!composing)$('discard-confirm').hidden=false;});
  $('discard-keep').addEventListener('click',()=>{$('discard-confirm').hidden=true;body.focus({preventScroll:true});});
  $('discard-yes').addEventListener('click',()=>{
    if (busy || composing || !editor) return;
    try {localStorage.removeItem(editor.key);if(localStorage.getItem(pointer)===editor.key)localStorage.removeItem(pointer);} catch {}
    editor=null;body.value='';host.hidden=true;$('discard-confirm').hidden=true;changed();core.announce('当前草稿已丢弃，未产生评论。');
  });
  $('annotation-conflict').addEventListener('click',async()=>{
    if (!editor || composing) return;
    const latest = await callbacks.latest?.(editor.thread,editor.item);
    if (!latest?.can_edit) {revoke(editor.thread);return;}
    $('conflict-content').textContent=latest.body;
    $('conflict-review').hidden=false;editor.pendingVersion=latest.version;
  });
  $('conflict-apply').addEventListener('click',()=>{
    if (!editor?.pendingVersion || composing) return;
    editor.version=editor.pendingVersion;delete editor.pendingVersion;
    $('conflict-review').hidden=true;$('annotation-conflict').hidden=true;
    status.textContent='已对照最新内容，请检查你的草稿后再次保存。';save();body.focus({preventScroll:true});
  });
  window.addEventListener('pagehide',save);
  window.GAReaderComposer={open,close,save,revoke,configure(value){callbacks=value;changed();},
    get editor(){return editor;},get visible(){return !host.hidden;},get composing(){return composing;},get busy(){return busy;}};
})();

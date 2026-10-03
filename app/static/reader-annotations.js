'use strict';
(() => {
  const core=window.GAReader;if(!core?.manifest)return;
  const $=id=>document.getElementById(id),node=core.node,api=core.api,article=core.article,reader=core.reader;
  const tools=$('selection-tools'),panel=$('annotation-panel'),rail=$('annotation-rail'),list=$('annotation-list');
  const body=$('annotation-body'),status=$('annotation-status'),overlay=$('annotation-overlays'),markers=$('annotation-markers');
  const retry=node('button','已对照最新内容，继续修改');retry.type='button';retry.hidden=true;status.after(retry);
  retry.addEventListener('click',async()=>{
    if(editor?.mode!=='edit')return;
    await refresh(true);
    const thread=notes.get(editor.thread),item=thread?.id===editor.item?thread:thread?.replies.find(r=>r.id===editor.item);
    if(!item?.can_edit){status.textContent='这条内容已删除、隐藏或失去编辑权限；草稿仍保留。';return;}
    if(!confirm('最新内容：\n\n'+item.body+'\n\n请先对照以上内容。继续使用你的草稿编辑？'))return;
    editor.version=item.version;saveDraft();retry.hidden=true;status.textContent='已载入最新版本号，请核对草稿后保存。';body.focus();
  });
  const precision={exact:'原选字 · 精确定位',aligned_exact:'已确认短语对齐',block:'段落对应',object:'对象批注',page:'仅定位到页',unmapped:'当前视图未定位',stale:'旧修订 · 待确认'};
  const notes=new Map(),textMaps=new WeakMap(),repElements=new Map([...article.querySelectorAll('[data-representation]')].map(el=>[el.dataset.representation,el]));
  const draftBase=`gareader:draft:v2:${reader.dataset.user}:${reader.dataset.paper}:`,lastDraft=draftBase+'last';
  let selection=null,hoverUnit=null,active=null,editor=null,inline=core.settings.inline!==false,panelFilter=null;
  let cursor=null,requestNumber=0,busy=false,geometryFrame=0,selectionTimer,hits=[],notePositions=new Map();
  let sourceLocated=false;
  const mapFor=el=>{if(!textMaps.has(el))textMaps.set(el,GAReaderText.logical(el));return textMaps.get(el);};
  const hasDraft=()=>!!(editor&&body.value.trim());
  const quoteOf=source=>source?.segments.map(s=>s.quote||s.label||(s.page_index!==undefined?'原版物理页 '+(s.page_index+1):'')).join(' … ')||'';
  const languageLabel=source=>source?.created_view==='pdf'?'原版 PDF':{zh:'中文',en:'英文',shared:'段落／对象',und:'原文'}[source?.source_language]||'';
  function saveDraft(){
    if(!editor)return;
    editor.body=body.value;
    try{localStorage.setItem(editor.key,JSON.stringify(editor));localStorage.setItem(lastDraft,editor.key);}catch{status.textContent='浏览器不能保存草稿；本页内仍保留，请及时提交。';}
  }
  function showPanel(ids=null){
    panelFilter=ids;panel.hidden=false;$('annotations-toggle').setAttribute('aria-expanded','true');
    tools.hidden=true;$('object-annotate').hidden=true;renderCards();scheduleGeometry();
  }
  function closePanel(){
    if(hasDraft()&&!confirm('草稿尚未提交，收起后会保留。继续收起？'))return;
    saveDraft();panel.hidden=true;$('annotations-toggle').setAttribute('aria-expanded','false');renderCards();scheduleGeometry();
  }
  async function editorKey(mode,source,item){
    if(mode!=='new')return draftBase+mode+':'+item.id;
    const encoded=new TextEncoder().encode(JSON.stringify(source));
    const hash=[...new Uint8Array(await crypto.subtle.digest('SHA-256',encoded))].map(n=>n.toString(16).padStart(2,'0')).join('');
    return draftBase+'new:'+hash;
  }
  async function openEditor({mode='new',source=null,item=null,thread=null}={}){
    const key=await editorKey(mode,source,item);
    if(editor?.key!==key&&hasDraft()){
      if(!confirm('当前草稿尚未提交；切换后会保留草稿。继续？'))return;
      saveDraft();
    }
    let old;
    try{old=JSON.parse(localStorage.getItem(key)||'null');}catch{}
    editor=old||{key,mode,source:source||thread?.source,thread:thread?.id||item?.id||null,item:item?.id||null,
      version:item?.version,body:mode==='edit'?item.body:'',request_key:crypto.randomUUID(),signature:''};
    if(thread)active=thread.id;
    body.value=editor.body||'';retry.hidden=true;
    $('annotation-editor').hidden=false;
    $('annotation-editor-title').textContent={new:'新建批注',reply:'回复批注',edit:'编辑自己的内容'}[mode];
    $('annotation-save').textContent={new:'保存批注',reply:'发表回复',edit:'保存修改'}[mode];
    $('annotation-editor-source').textContent=languageLabel(editor.source)+' · '+(editor.source?.segments.map(s=>s.unit_id||('物理页 '+(s.page_index+1))).join('、')||'');
    $('annotation-quote').textContent=quoteOf(editor.source);status.textContent='';showPanel();saveDraft();body.focus();
  }
  function sourceFromHTML(range){
    if(!article.contains(range.startContainer)||!article.contains(range.endContainer))throw Error('请只选择一种语言内的正文，不要混选工具栏。');
    const owner=n=>n.nodeType===Node.ELEMENT_NODE?n:n.parentElement;
    if(!owner(range.startContainer).closest('[data-representation]')||!owner(range.endContainer).closest('[data-representation]'))throw Error('请从同一种语言的正文开始并结束选择；段落或公式可使用对象批注。');
    if([...article.querySelectorAll('math')].some(m=>m.getClientRects().length&&range.intersectsNode(m)))throw Error('选区包含公式，请使用旁边的段落／公式对象批注入口。');
    const segments=[],languages=new Set();
    for(const [rid,el] of repElements){
      if(!el.getClientRects().length||!range.intersectsNode(el))continue;
      const selected=GAReaderText.selected(range,mapFor(el));if(!selected)continue;
      const rep=core.manifest.representations[rid];languages.add(rep.language);
      const math=[...el.querySelectorAll('math')].some(m=>selected.range.intersectsNode(m));
      if(math)throw Error('选区包含公式，请使用旁边的段落／公式对象批注入口。');
      segments.push({unit_id:rep.unit_id,representation_id:rid,start:selected.start,end:selected.end,quote:selected.quote,
        raw_quote:selected.raw_quote,text_hash:rep.text_hash,normalization_version:GAReaderText.NORMALIZATION});
    }
    if(languages.size!==1)throw Error('一次只能选择中文或英文中的一种语言，请重新选择。');
    if(!segments.length||segments.length>32)throw Error('请选择 1—32 个同语言内容片段。');
    if(segments.reduce((sum,s)=>sum+[...s.quote].length,0)>20000)throw Error('选区超过 20000 字，请分段批注。');
    return {revision_id:reader.dataset.revision,created_view:core.view,source_language:[...languages][0],kind:'text',segments};
  }
  function captureSelection(showError=false){
    const chosen=window.getSelection();
    if(!chosen||chosen.isCollapsed||chosen.rangeCount!==1){tools.hidden=true;return;}
    const range=chosen.getRangeAt(0),surface=core.view==='pdf'?$('pdf-reader'):article;
    if(!surface.contains(range.startContainer)&&!surface.contains(range.endContainer)){tools.hidden=true;return;}
    if(!surface.contains(range.startContainer)||!surface.contains(range.endContainer)){tools.hidden=true;if(showError)core.announce('请只选择正文，不要混选工具栏。');return;}
    try{
      const owner=n=>n.nodeType===Node.ELEMENT_NODE?n:n.parentElement;
      if(core.view==='pdf'&&(!owner(range.startContainer).closest('.textLayer')||!owner(range.endContainer).closest('.textLayer')))throw Error('请从 PDF 文字层开始并结束选择。');
      const source=core.view==='pdf'?GAReaderPDF.sourceSelection(range):sourceFromHTML(range);
      const rects=[...range.getClientRects()].filter(r=>r.width>0&&r.height>0&&r.bottom>document.querySelector('.readerbar').getBoundingClientRect().bottom&&r.top<innerHeight);
      const rect=rects.at(-1);if(!rect){tools.hidden=true;return;}
      selection={source,text:source.segments.map(s=>s.raw_quote||s.quote).join('\n'),range:range.cloneRange()};
      tools.hidden=false;
      const width=tools.offsetWidth,height=tools.offsetHeight,topBar=document.querySelector('.readerbar').getBoundingClientRect().bottom;
      tools.style.left=Math.max(8,Math.min(innerWidth-width-8,rect.left))+'px';
      tools.style.top=Math.max(topBar+6,Math.min(innerHeight-height-8,rect.bottom+height+12<innerHeight?rect.bottom+8:rect.top-height-8))+'px';
    }catch(error){tools.hidden=true;selection=null;if(showError)core.announce(error.message);}
  }
  tools.addEventListener('pointerdown',e=>e.preventDefault());
  $('selection-annotate').addEventListener('click',()=>{if(selection)openEditor({source:selection.source});});
  $('selection-copy').addEventListener('click',async()=>{if(!selection)return;try{await navigator.clipboard.writeText(selection.text);core.announce('已复制选中文字。');}catch{core.announce('无法自动复制，请使用 Ctrl+C。');}});
  $('selection-google').addEventListener('click',()=>{if(selection)window.GAReaderGoogle?.search(selection.text);});
  document.addEventListener('selectionchange',()=>{clearTimeout(selectionTimer);selectionTimer=setTimeout(()=>captureSelection(),100);});
  document.addEventListener('pointerup',e=>{
    if(!article.contains(e.target)&&!$('pdf-reader').contains(e.target))return;
    clearTimeout(selectionTimer);selectionTimer=setTimeout(()=>captureSelection(true),30);
    if(window.getSelection()?.isCollapsed&&inline){
      const ids=[...new Set(hits.filter(h=>e.clientX>=h.rect.left&&e.clientX<=h.rect.right&&e.clientY>=h.rect.top&&e.clientY<=h.rect.bottom).map(h=>h.id))];
      if(ids.length){active=ids[0];showPanel(ids);}
    }
  });
  article.addEventListener('pointermove',event=>{
    const unit=event.target.closest('[data-unit]');if(!unit||!panel.hidden&&innerWidth<1700||!tools.hidden)return;
    hoverUnit=unit.dataset.unit;const rect=unit.getBoundingClientRect(),button=$('object-annotate');
    button.hidden=false;button.style.top=Math.max(document.querySelector('.readerbar').getBoundingClientRect().bottom+4,rect.top)+'px';
    button.style.left=Math.max(5,Math.min(innerWidth-button.offsetWidth-8,rect.right-80))+'px';
  });
  $('object-annotate').addEventListener('click',()=>{
    if(hoverUnit)openEditor({source:{revision_id:reader.dataset.revision,created_view:core.view,source_language:'shared',kind:'object',segments:[{unit_id:hoverUnit}]}});
  });
  // Keyboard users can create an object annotation from the focused article unit.
  for(const el of article.querySelectorAll('[data-unit]')){
    el.tabIndex=0;el.addEventListener('keydown',e=>{if(e.altKey&&e.key.toLowerCase()==='a'){e.preventDefault();hoverUnit=el.dataset.unit;$('object-annotate').click();}});
  }
  document.addEventListener('gareader:pdf-page-note',event=>openEditor({source:{revision_id:reader.dataset.revision,
    created_view:'pdf',source_language:'und',kind:'pdf_page',pdf_sha256:core.manifest.pdf_sha256,
    coordinate_system:'pdf-user-space',segments:[{page_index:event.detail.page_index}]}}));
  function primaryPrecision(note){return note.projections.find(p=>p.precision==='exact')||note.projections.find(p=>!['stale','unmapped'].includes(p.precision))||note.projections[0]||{precision:'unmapped'};}
  function makeCard(note){
    const card=node('article',undefined,'annotation-card'+(active===note.id?' active':''));card.dataset.thread=note.id;
    const meta=node('header',undefined,'annotation-meta');meta.append(node('strong',note.author),node('small',languageLabel(note.source)+' · '+note.created_at));card.append(meta);
    if(note.source)meta.append(node('small',note.source.segments.map(s=>s.page_index!==undefined?'物理页 '+(s.page_index+1):'段落 '+s.unit_id.replace(/^p-/, '')).join(' · ')));
    const p=primaryPrecision(note),badge=node('span',precision[p.precision]||p.precision,'precision-badge '+p.precision);badge.title=p.reason||'';card.append(badge);
    if(note.source)card.append(node('blockquote',quoteOf(note.source),'annotation-quote'));
    card.append(node('p',note.body===null?note.placeholder:note.body,'annotation-content'));
    const actions=node('div',undefined,'annotation-actions');card.append(actions);
    function action(label,fn,target=actions){const button=node('button',label);button.type='button';button.addEventListener('click',async()=>{button.disabled=true;try{await fn();}catch(error){status.textContent=error.message||'未保存，请重试。';}finally{button.disabled=false;}});target.append(button);}
    if(note.source){action('在文中显示',()=>locate(note));const back=node('a','回到来源');back.href=note.source_url;actions.append(back);}
    if(note.body!==null)action('回复',()=>openEditor({mode:'reply',item:note,thread:note}));
    async function remove(item){if(!confirm('删除这条内容？已有回复会保留。'))return;await api(`comments/${item.id}/`,'DELETE',{version:item.version});await refresh(true);}
    if(note.can_edit){action('编辑',()=>openEditor({mode:'edit',item:note,thread:note}));action('删除',()=>remove(note));}
    if(note.can_hide)action(note.hidden?'恢复显示':'隐藏',async()=>{await api(`comments/${note.id}/hide/`,'POST',{hidden:!note.hidden,version:note.version});await refresh(true);});
    if(note.replies.length){
      const replies=node('details',undefined,'annotation-replies');replies.open=note.id===active;
      replies.append(node('summary',`${note.replies.length} 条回复`));
      for(const reply of note.replies){
        const block=node('div',undefined,'annotation-reply');block.append(node('strong',reply.author),node('p',reply.body===null?reply.placeholder:reply.body));
        if(reply.can_edit){action('编辑',()=>openEditor({mode:'edit',item:reply,thread:note}),block);action('删除',()=>remove(reply),block);}
        if(reply.can_hide)action(reply.hidden?'恢复':'隐藏',async()=>{await api(`comments/${reply.id}/hide/`,'POST',{hidden:!reply.hidden,version:reply.version});await refresh(true);},block);
        replies.append(block);
      }
      replies.addEventListener('toggle',scheduleGeometry);card.append(replies);
    }
    return card;
  }
  function renderCards(){
    list.replaceChildren();rail.replaceChildren();
    const wide=inline&&innerWidth>=1700&&panel.hidden&&notes.size>0;
    rail.hidden=!wide;$('reading-layout').classList.toggle('with-rail',wide);
    const ordered=[...notes.values()].sort((a,b)=>a.id-b.id);
    if(!panel.hidden){
      const shown=panelFilter?ordered.filter(n=>panelFilter.includes(n.id)):ordered;
      for(const note of shown)list.append(makeCard(note));
      if(!shown.length)list.append(node('p','还没有批注。选择正文或使用段落旁的 ＋ 批注。','muted'));
    }else if(wide){
      for(const note of ordered.filter(n=>n.projections.some(p=>!['unmapped','stale'].includes(p.precision))))rail.append(makeCard(note));
    }
    core.sizing();scheduleGeometry();
  }
  async function refresh(full=false){
    const number=++requestNumber,view=core.view;
    const query=new URLSearchParams({revision:reader.dataset.revision,view});
    if(!full&&cursor)query.set('since',cursor);
    try{
      const result=await api('annotations/?'+query);
      if(number!==requestNumber||view!==core.view)return;
      if(full)notes.clear();for(const note of result.threads)notes.set(note.id,note);
      cursor=result.cursor;$('annotation-count').textContent=result.count;
      renderCards();
      const params=new URLSearchParams(location.search),requested=Number(params.get('thread'));
      if(!sourceLocated&&notes.has(requested)&&(!params.get('view')||params.get('view')===view)){
        sourceLocated=true;active=requested;showPanel([requested]);await locate(notes.get(requested),{enable:false});
      }
    }catch(error){status.textContent=error.message||'批注加载失败，请重试。';}
  }
  function setInline(enabled){
    inline=enabled;core.settings.inline=inline;core.persist();
    $('inline-toggle').textContent='页内批注：'+(inline?'开':'关');$('inline-toggle').setAttribute('aria-pressed',String(inline));
    reader.classList.toggle('inline-off',!inline);renderCards();
  }
  function rangeFor(p){
    const element=repElements.get(p.representation_id);if(!element||!element.getClientRects().length)return null;
    const map=mapFor(element);if(map.chars.slice(p.start,p.end).join('')!==p.quote)return null;
    return GAReaderText.restore(map,p.start,p.end);
  }
  function rectsFor(p){
    if(core.view==='pdf')return window.GAReaderPDF?.projectedRects(p)||[];
    if(p.precision==='exact'){const range=rangeFor(p);return range?[...range.getClientRects()]:[];}
    const unit=document.getElementById(p.unit_id);if(!unit)return [];
    let el=unit;
    if(p.language&&p.language!=='shared'){
      const pieces=[...unit.querySelectorAll('[data-rep-language]')].filter(x=>x.dataset.repLanguage===p.language&&x.getClientRects().length);
      if(pieces.length)return pieces.map(x=>x.getBoundingClientRect());
    }
    if(!el.getClientRects().length)return [];
    return [el.getBoundingClientRect()];
  }
  function clipped(rect){
    const clip=core.view==='pdf'?$('pdf-reader').getBoundingClientRect():{left:0,right:innerWidth};
    const left=Math.max(0,clip.left,rect.left),right=Math.min(innerWidth,clip.right,rect.right);
    return {left,right,top:rect.top,bottom:rect.bottom,width:right-left,height:rect.bottom-rect.top};
  }
  function paintGeometry(){
    geometryFrame=0;overlay.replaceChildren();markers.replaceChildren();hits=[];notePositions=new Map();
    if(globalThis.CSS?.highlights){CSS.highlights.delete('annotations');CSS.highlights.delete('annotation-active');}
    if(!inline)return;
    const ranges=[],activeRanges=[],groups=new Map();
    for(const note of notes.values())for(const projection of note.projections){
      if(['unmapped','stale'].includes(projection.precision))continue;
      if(core.view!=='pdf'&&projection.precision==='exact'){
        const range=rangeFor(projection);if(range){ranges.push(range);if(note.id===active)activeRanges.push(range);}
      }
      const rects=rectsFor(projection).filter(r=>r.width>0&&r.height>0).map(clipped).filter(r=>r.width>0);
      if(!rects.length)continue;
      notePositions.set(note.id,Math.min(notePositions.get(note.id)||Infinity,rects[0].top+scrollY));
      const key=core.view==='pdf'?`pdf:${projection.page_index}:${Math.round(rects[0].top/22)}`:`${projection.unit_id}:${projection.language}`;
      if(!groups.has(key))groups.set(key,{rect:rects[0],ids:new Set(),precision:projection.precision});
      groups.get(key).ids.add(note.id);
      for(const rect of rects){
        hits.push({id:note.id,rect});
        if(core.view!=='pdf'&&projection.precision==='exact'&&globalThis.CSS?.highlights)continue;
        const mark=node('div',undefined,'annotation-geometry '+projection.precision+(note.id===active?' active':''));
        Object.assign(mark.style,{left:rect.left+'px',top:rect.top+'px',width:rect.width+'px',height:rect.height+'px'});overlay.append(mark);
      }
    }
    if(globalThis.CSS?.highlights&&globalThis.Highlight){CSS.highlights.set('annotations',new Highlight(...ranges));CSS.highlights.set('annotation-active',new Highlight(...activeRanges));}
    const toolbarBottom=document.querySelector('.readerbar').getBoundingClientRect().bottom;
    for(const group of groups.values()){
      if(group.rect.bottom<toolbarBottom||group.rect.top>innerHeight)continue;
      const ids=[...group.ids],button=node('button',String(ids.length),'annotation-marker');
      button.type='button';button.setAttribute('aria-label',`${ids.length} 条批注 · ${precision[group.precision]}`);button.title=precision[group.precision];
      Object.assign(button.style,{left:Math.max(2,Math.min(innerWidth-30,group.rect.right+4))+'px',top:Math.max(toolbarBottom+3,group.rect.top)+'px'});
      button.addEventListener('click',()=>{active=ids[0];showPanel(ids);});markers.append(button);
    }
    if(!rail.hidden){
      const start=$('reading-layout').getBoundingClientRect().top+scrollY;let bottom=0;
      const cards=[...rail.children].sort((a,b)=>(notePositions.get(Number(a.dataset.thread))||0)-(notePositions.get(Number(b.dataset.thread))||0));
      for(const card of cards){const y=Math.max(bottom,(notePositions.get(Number(card.dataset.thread))||start)-start);card.style.top=y+'px';bottom=y+card.offsetHeight+16;}
    }
  }
  function scheduleGeometry(){if(!geometryFrame)geometryFrame=requestAnimationFrame(paintGeometry);}
  async function locate(note,{enable=true}={}){
    active=note.id;if(!inline&&enable)setInline(true);
    const target=note.projections.find(p=>!['stale','unmapped'].includes(p.precision));
    if(!target){status.textContent=primaryPrecision(note).reason||'当前视图未定位，可回到来源。';return;}
    if(core.view==='pdf'){await GAReaderPDF.locate(target);}
    else {
      const el=document.getElementById(target.unit_id);let details=el?.closest('details');while(details){details.open=true;details=details.parentElement.closest('details');}
      el?.scrollIntoView({block:'center'});
    }
    renderCards();scheduleGeometry();
  }
  $('annotation-form').addEventListener('submit',async event=>{
    event.preventDefault();if(!editor||busy||!body.value.trim())return;
    saveDraft();busy=true;$('annotation-save').disabled=true;status.textContent='正在保存…';
    const submitted={...editor,body:body.value.trim()};
    try{
      let result;
      if(submitted.mode==='edit')result=await api(`comments/${submitted.item}/`,'PATCH',{body:submitted.body,version:submitted.version});
      else {
        const signature=JSON.stringify([submitted.body,submitted.source,submitted.thread]);
        if(editor.signature!==signature){editor.signature=signature;editor.request_key=crypto.randomUUID();saveDraft();}
        if(submitted.mode==='new')result=await api('annotations/','POST',{body:submitted.body,source:submitted.source,request_key:editor.request_key});
        else result=await api('comments/','POST',{body:submitted.body,parent:submitted.thread,request_key:editor.request_key});
      }
      active=submitted.mode==='new'?result.id:submitted.thread;
      try{localStorage.removeItem(editor.key);localStorage.removeItem(lastDraft);}catch{}
      editor=null;body.value='';$('annotation-editor').hidden=true;panelFilter=null;
      status.textContent=inline?'已保存。':'已保存，当前页内显示关闭。';await refresh(true);
    }catch(error){status.textContent=error.message||'连接失败，未保存；草稿已保留，可安全重试。';retry.hidden=!(error.status===409&&editor?.mode==='edit');saveDraft();}
    finally{busy=false;$('annotation-save').disabled=false;}
  });
  body.addEventListener('input',saveDraft);
  $('annotation-cancel').addEventListener('click',()=>{if(hasDraft()&&!confirm('草稿尚未提交，将保留在本浏览器。继续收起？'))return;saveDraft();$('annotation-editor').hidden=true;status.textContent='草稿已保留。';});
  $('inline-toggle').addEventListener('click',()=>setInline(!inline));
  $('annotations-toggle').addEventListener('click',()=>{showPanel();if(editor){$('annotation-editor').hidden=false;body.value=editor.body||'';}});
  $('annotations-close').addEventListener('click',closePanel);
  window.addEventListener('beforeunload',event=>{saveDraft();if(hasDraft()){event.preventDefault();event.returnValue='';}});
  window.addEventListener('scroll',()=>{tools.hidden=true;$('object-annotate').hidden=true;scheduleGeometry();},{passive:true});
  window.addEventListener('resize',()=>{tools.hidden=true;renderCards();scheduleGeometry();});
  document.addEventListener('gareader:layout',scheduleGeometry);document.addEventListener('gareader:pdf-rendered',scheduleGeometry);
  document.addEventListener('gareader:view',()=>{tools.hidden=true;$('object-annotate').hidden=true;saveDraft();cursor=null;refresh(true);});
  document.addEventListener('keydown',event=>{if(event.key==='Escape'){tools.hidden=true;$('object-annotate').hidden=true;}});
  setInterval(()=>{if(!document.hidden)refresh();},25000);
  document.addEventListener('visibilitychange',()=>{if(!document.hidden)refresh();});
  try{const saved=JSON.parse(localStorage.getItem(localStorage.getItem(lastDraft))||'null');if(saved?.key?.startsWith(draftBase)){editor=saved;body.value=saved.body||'';$('annotation-editor-title').textContent='继续未提交的草稿';$('annotation-quote').textContent=quoteOf(saved.source);$('annotation-editor-source').textContent=languageLabel(saved.source);}}catch{}
  setInline(inline);refresh(true);if(location.hash==='#annotations')showPanel();
  window.GAReaderAnnotations={refresh,openEditor,setInline,locate,get notes(){return notes;},get selection(){return selection;},get editor(){return editor;},paintGeometry};
})();

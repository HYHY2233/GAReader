'use strict';
(() => {
  const core=window.GAReader;if(!core?.manifest)return;
  const $=id=>document.getElementById(id),node=core.node,api=core.api,article=core.article,reader=core.reader;
  const composer=window.GAReaderComposer,geometry=window.GAReaderGeometry,navigation=window.GAReaderNavigation;
  const tools=$('selection-tools'),rail=$('annotation-rail'),overview=$('annotation-overview'),list=$('annotation-list'),floating=$('annotation-inline'),inlineHost=$('inline-thread'),picker=$('annotation-picker');
  const presentation=window.GAAnnotationPresentation,notes=new Map(),textMaps=new WeakMap();
  const repElements=new Map([...article.querySelectorAll('[data-representation]')].map(el=>[el.dataset.representation,el]));
  const caches=new Map([[rail,new Map()],[list,new Map()],[inlineHost,new Map()]]),collapsed=new Set();
  let selection=null,hoverUnit=null,active=null,activeSegment=null,inline=core.settings.inline!==false,focus=null,single=false,cursor=null,requestNumber=0,inflight=null,initialized=false,selectionTimer;
  const mapFor=el=>{if(!textMaps.has(el))textMaps.set(el,GAReaderText.logical(el));return textMaps.get(el);};
  function context(){return {revision:reader.dataset.revision,view:core.view,pdfHash:core.manifest.pdf_sha256,
    units:new Set([...article.querySelectorAll('[data-unit]')].filter(e=>e.getClientRects().length).map(e=>e.dataset.unit)),
    representations:new Set([...repElements].filter(([,e])=>e.getClientRects().length).map(([id])=>id))};}
  function primary(note){return geometry.plan(note)[0]?.projection||{precision:'unmapped'};}
  function precisionLabel(note){const targets=geometry.plan(note),kinds=[...new Set(targets.map(t=>t.precision))];
    if(kinds.length<2)return presentation.precision[kinds[0]]||'当前视图未定位';
    return [...new Set(targets.map(t=>`片段 ${t.source_segment_index+1}：${presentation.precision[t.precision]||'当前视图未定位'}`))].join('；');}
  function button(label,key,action){const b=node('button',label);b.type='button';b.dataset.action=key;b.addEventListener('click',async()=>{if(composer.composing)return;b.disabled=true;try{await action();}catch(e){core.announce(e.message||'操作未完成，请重试。');}finally{b.disabled=false;}});return b;}
  function objects(note){
    const box=node('div',undefined,'annotation-objects');
    note.source?.segments.forEach((segment,index)=>{
      const row=node('div',undefined,'annotation-object'),label=presentation.objectLabel(segment,index,note.source.segments.length);
      const link=button(label,'source-'+index,()=>navigation.source(note,index));link.className='source-object';row.append(link);
      if(label.length>65){const expand=button('展开完整引用','expand-'+index,()=>{const full=row.classList.toggle('expanded');expand.textContent=full?'收起完整引用':'展开完整引用';geometry.schedule();});row.append(expand);}
      box.append(row);
    });return box;
  }
  function footer(item){const el=node('footer',`来自 ${item.author} · ${presentation.localTime(item)}${item.edited?' · 已编辑':''}`,'annotation-footer');el.title=item.created_at_iso||item.created_at;return el;}
  function card(note,ctx){
    const root=node('article',undefined,'annotation-card');root.dataset.thread=note.id;root.tabIndex=0;
    const relation=presentation.relation(note.source,ctx),p=primary(note);root.dataset.relationship=relation;root.dataset.precision=p.precision;
    if(relation!=='direct'){
      root.append(node('h3',relation==='old_revision'?`来自旧修订（${presentation.sourceName(note.source)}）的批注`:relation==='unavailable'?'来源已不可访问':`来自${presentation.sourceName(note.source)}的批注`,'annotation-origin'));
      if(note.source){root.append(node('p','批注对象：','annotation-label'),objects(note));}
      root.append(node('p','批注内容：','annotation-label'));
    }
    root.append(node('p',note.body===null?note.placeholder:note.body,'annotation-content'));
    if(relation!=='direct')root.append(node('p',precisionLabel(note),'precision-label'));
    if(relation==='direct'&&note.source){const details=node('details',undefined,'annotation-details');details.dataset.state='objects';details.append(node('summary','查看批注对象'),objects(note),node('p',precisionLabel(note)));root.append(details);}
    const actions=node('div',undefined,'annotation-actions');root.append(actions);
    if(note.source)actions.append(button('回复','reply',()=>composer.open({mode:'reply',item:note,thread:note})));
    actions.append(button('收起','collapse',()=>{collapsed.add(note.id);if(active===note.id)active=null;render();}));
    actions.append(button('定位这条批注','locate',()=>locate(note)));
    function editActions(item,host){
      if(item.can_edit){host.append(button('编辑','edit-'+item.id,()=>composer.open({mode:'edit',item,thread:note})));
        const removal=node('div',undefined,'annotation-removal');removal.hidden=true;
        host.append(button('删除','remove-'+item.id,()=>{removal.hidden=!removal.hidden;geometry.schedule();}));
        removal.append(node('p','确认删除自己的这条内容？已有可见回复会保留。'),button('确认删除','delete-'+item.id,async()=>{await api(`comments/${item.id}/`,'DELETE',{version:item.version});await refresh({thread:note.id});}),button('取消','keep-'+item.id,()=>{removal.hidden=true;geometry.schedule();}));host.append(removal);}
      if(item.can_hide)host.append(button(item.hidden?'恢复显示':'隐藏','hide-'+item.id,async()=>{await api(`comments/${item.id}/hide/`,'POST',{hidden:!item.hidden,version:item.version});await refresh({thread:note.id});}));
    }
    editActions(note,actions);root.append(footer(note));
    if(note.replies.length){const details=node('details',undefined,'annotation-replies');details.dataset.state='replies';details.append(node('summary',`${note.replies.filter(r=>r.body!==null).length} 条可见回复`));
      for(const reply of note.replies){const row=node('section',undefined,'annotation-reply');row.dataset.reply=reply.id;row.append(node('p',reply.body===null?reply.placeholder:reply.body),footer(reply));editActions(reply,row);details.append(row);}root.append(details);}
    root.addEventListener('toggle',geometry.schedule,true);
    const selectCard=async event=>{if(composer.visible||composer.composing||event.target.closest('button,a,input,textarea,select,summary')||event.type==='focusin'&&event.target!==root)return;
      const id=Number(root.dataset.thread),current=notes.get(id);if(!current||active===id)return;
      const keepFocus=event.type==='focusin';
      if(geometry.targets.some(t=>t.thread_id===id))activate(id);else await locate(current);
      if(keepFocus){await new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)));
        if(active===id&&!composer.visible)[...document.querySelectorAll(`.annotation-card[data-thread="${id}"]`)].find(e=>e.getClientRects().length)?.focus({preventScroll:true});}
    };
    root.addEventListener('click',selectCard);root.addEventListener('focusin',selectCard);return root;
  }
  function sync(host,ids,ctx=context()){
    const cache=caches.get(host),keep=new Set(ids);
    for(const [id,entry] of cache)if(!keep.has(id)){geometry.unobserve(entry.el);entry.el.remove();cache.delete(id);}
    for(const id of ids){const note=notes.get(id);if(!note)continue;
      const signature=JSON.stringify([note,presentation.relation(note.source,ctx),core.view]);let entry=cache.get(id);
      if(!entry){const el=card(note,ctx);entry={el,signature};cache.set(id,entry);host.append(el);geometry.observe(el);}
      else if(entry.signature!==signature){
        const focused=entry.el.contains(document.activeElement)?document.activeElement.dataset.action:null;
        const opened=new Set([...entry.el.querySelectorAll('details[open]')].map(e=>e.dataset.state));
        const expanded=new Set([...entry.el.querySelectorAll('.annotation-object.expanded')].map(e=>e.querySelector('button').dataset.action));
        const fresh=card(note,ctx);entry.el.replaceChildren(...fresh.childNodes);entry.el.dataset.relationship=fresh.dataset.relationship;entry.el.dataset.precision=fresh.dataset.precision;entry.signature=signature;
        for(const details of entry.el.querySelectorAll('details'))details.open=opened.has(details.dataset.state);
        for(const obj of entry.el.querySelectorAll('.annotation-object'))if(expanded.has(obj.querySelector('button').dataset.action)){obj.classList.add('expanded');const b=obj.querySelector('button[data-action^="expand-"]');if(b)b.textContent='收起完整引用';}
        if(focused)[...entry.el.querySelectorAll('[data-action]')].find(e=>e.dataset.action===focused)?.focus({preventScroll:true});
      }
      entry.el.classList.toggle('active',id===active);
    }
    const ordered=ids.map(id=>cache.get(id)?.el).filter(Boolean);
    ordered.forEach((el,index)=>{if(host.children[index]!==el)host.insertBefore(el,host.children[index]||null);});
  }
  function closeOverview(){overview.hidden=true;$('annotations-toggle').setAttribute('aria-expanded','false');}
  function render(){
    if(!overview.hidden){sync(list,[...notes.keys()].sort((a,b)=>a-b));$('overview-empty').hidden=notes.size>0;}
    $('continue-draft').hidden=!composer.editor||composer.visible;
    geometry.schedule();
  }
  function surfaceLayout(positions,draftTargets=[],{hasTargets=false}={}){
    const draftRects=draftTargets.flatMap(t=>t.rects);
    const layout=$('reading-layout'),width=layout.clientWidth,canRail=width>=Math.max(440,16*core.font)+350+24;
    const editorOpen=composer.visible;
    const eligible=[...positions.keys()].filter(id=>notes.has(id)&&!collapsed.has(id));
    eligible.sort((a,b)=>positions.get(a)[0].rects[0].top-positions.get(b)[0].rects[0].top||a-b);
    let ids=[];
    if(!editorOpen&&overview.hidden&&(inline||focus)){
      if(single)ids=active&&eligible.includes(active)?[active]:[];
      else {ids=eligible.slice(0,2);if(active&&eligible.includes(active)&&!ids.includes(active))ids=[active,...ids.slice(0,1)];}
    }
    const reserve=canRail&&overview.hidden&&(editorOpen||inline&&hasTargets);
    if(layout.classList.contains('with-rail')!==reserve){layout.classList.toggle('with-rail',reserve);core.sizing();return {cards:[],changed:true};}
    layout.classList.toggle('with-rail',reserve);rail.hidden=!reserve||editorOpen;
    const composerEl=$('annotation-composer');composerEl.classList.toggle('in-gutter',reserve&&editorOpen);
    if(editorOpen&&reserve){const r=layout.getBoundingClientRect();composerEl.style.left=(r.right-parseFloat(getComputedStyle(layout).paddingRight)-338)+'px';composerEl.style.right='auto';
      const top=document.querySelector('.readerbar').getBoundingClientRect().bottom+14,anchor=draftRects.at(-1)?.top||top;
      composerEl.style.top=Math.max(top,Math.min(innerHeight-composerEl.offsetHeight-16,anchor-24))+'px';}
    else {composerEl.style.left='';composerEl.style.right='';composerEl.style.top='';}
    if(editorOpen||!overview.hidden){sync(rail,[]);sync(inlineHost,[]);floating.hidden=true;return {cards:editorOpen?[{id:'composer',element:composerEl}]:[]};}
    const ctx=context();
    if(reserve){
      floating.hidden=true;sync(inlineHost,[]);sync(rail,ids,ctx);
      const top=document.querySelector('.readerbar').getBoundingClientRect().bottom+14,railTop=rail.getBoundingClientRect().top;
      const measured=ids.map(id=>({id,element:caches.get(rail).get(id)?.el,anchor:positions.get(id)?.[0]?.rects[0]?.top||top})).filter(x=>x.element).map(x=>({...x,height:x.element.getBoundingClientRect().height}));
      let edge=top;
      for(const item of measured){const y=Math.max(edge,item.anchor,top);item.element.style.top=(y-railTop)+'px';item.element.hidden=y>innerHeight-50&&item.id!==active;edge=y+item.height+14;}
      return {cards:measured.filter(x=>!x.element.hidden)};
    }
    sync(rail,[]);const id=active&&ids.includes(active)?active:null;floating.hidden=!id;
    sync(inlineHost,id?[id]:[],ctx);return {cards:id?[{id,element:caches.get(inlineHost).get(id).el}]:[]};
  }
  function activate(id,segment=null){active=id;activeSegment=segment;single=true;collapsed.delete(id);closeOverview();picker.hidden=true;render();}
  async function refresh({full=false,thread=null}={}){
    if(inflight&&!full&&!thread)return inflight;
    const number=++requestNumber,view=core.view,query=new URLSearchParams({revision:reader.dataset.revision,view});
    if(thread)query.set('thread',thread);else if(!full&&cursor)query.set('since',cursor);
    const task=(async()=>{try{
      const result=await api('annotations/?'+query);if(number!==requestNumber||view!==core.view)return;
      const incoming=new Set(result.threads.map(n=>n.id));
      const removed=new Set(result.removed_ids||[]);if(full&&!thread)for(const id of notes.keys())if(!incoming.has(id))removed.add(id);
      for(const id of removed){notes.delete(id);composer.revoke(id);if(active===id){active=null;focus=null;core.announce('当前讨论已删除或不可见；草稿保留。');}}
      for(const note of result.threads){notes.set(note.id,note);if(!note.source)composer.revoke(note.id);}
      if(!thread)cursor=result.cursor;$('annotation-count').textContent=result.count;render();
    }catch(error){if([401,403,404].includes(error.status)){for(const id of notes.keys())composer.revoke(id);composer.revoke(null);notes.clear();active=null;focus=null;render();}core.announce(error.message||'讨论加载失败，草稿仍保留。');}finally{if(number===requestNumber)inflight=null;}})();
    inflight=task;return task;
  }
  function setInline(value){inline=value;core.settings.inline=inline;core.persist();$('inline-toggle').textContent='页内批注：'+(inline?'开':'关');$('inline-toggle').setAttribute('aria-pressed',String(inline));reader.classList.toggle('inline-off',!inline);if(!inline){focus=null;active=null;$('focus-clear').hidden=true;}render();}
  async function locate(note,{segment=null,isCurrent=()=>true,temporary=true}={}){
    if(!isCurrent())return;activate(note.id);
    const candidates=geometry.plan(note).filter(t=>segment===null||t.source_segment_index===segment);
    const chosen=candidates.find(t=>GAAnnotationDisplay.drawable(t.projection)),target=chosen?.projection;
    activeSegment=chosen?.source_segment_index??segment;
    if(!target){core.announce(primary(note).reason||'当前视图未定位，请通过批注对象返回来源。');return false;}
    if(core.view==='pdf')await window.GAReaderPDF.locate(target,{isCurrent});
    else {
      const el=document.getElementById(target.unit_id);let details=el?.closest('details');while(details){details.open=true;details=details.parentElement.closest('details');}
      // A long paragraph may extend beyond the viewport: navigate to the actual selected line.
      await new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)));if(!isCurrent())return;
      const range=geometry.rangeFor(target);
      if(['exact','aligned_exact'].includes(target.precision)&&!range){core.announce('原选区与当前文字不匹配，请打开批注来源核对。');return false;}
      const rect=range?[...range.getClientRects()].find(r=>r.width>0&&r.height>0):el?.getBoundingClientRect();
      if(rect){const bar=document.querySelector('.readerbar').getBoundingClientRect().bottom;window.scrollTo({top:scrollY+rect.top-bar-Math.min(100,(innerHeight-bar)/4),behavior:'instant'});}
    }
    if(!isCurrent())return;
    if(temporary&&!inline){focus={id:note.id,segment:chosen.source_segment_index};$('focus-clear').hidden=false;}
    render();return true;
  }
  function choose(ids,opener,segments={}){
    if(ids.length===1){activate(ids[0],segments[ids[0]]??null);return;}
    picker.replaceChildren(node('p',`此处 ${ids.length} 条讨论`));
    for(const id of ids){const note=notes.get(id);if(note)picker.append(button(`${note.author}：${(note.body||note.placeholder).slice(0,70)}`,'choose-'+id,()=>{activate(id,segments[id]??null);geometry.schedule();}));}
    picker.hidden=false;const r=opener.getBoundingClientRect();picker.style.top=Math.min(innerHeight-picker.offsetHeight-12,r.bottom+6)+'px';picker.style.left=Math.max(8,Math.min(innerWidth-picker.offsetWidth-8,r.left))+'px';picker.querySelector('button')?.focus({preventScroll:true});
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
  $('selection-annotate').addEventListener('click',()=>{if(selection)composer.open({source:selection.source});});
  $('selection-copy').addEventListener('click',async()=>{if(!selection)return;try{await navigator.clipboard.writeText(selection.text);core.announce('已复制选中文字。');}catch{core.announce('无法自动复制，请使用 Ctrl+C。');}});
  $('selection-google').addEventListener('click',()=>{if(selection)window.GAReaderGoogle?.search(selection.text);});
  document.addEventListener('selectionchange',()=>{clearTimeout(selectionTimer);selectionTimer=setTimeout(()=>captureSelection(),100);});
  document.addEventListener('pointerup',e=>{
    if(!article.contains(e.target)&&!$('pdf-reader').contains(e.target))return;
    clearTimeout(selectionTimer);selectionTimer=setTimeout(()=>captureSelection(true),30);
    if(window.getSelection()?.isCollapsed&&inline&&!composer.visible){const targets=geometry.hitTargets(e.clientX,e.clientY),ids=[...new Set(targets.map(t=>t.id))];if(ids.length)choose(ids,e.target,Object.fromEntries(targets.map(t=>[t.id,t.source_segment_index])));}
  });
  article.addEventListener('pointermove',event=>{
    const unit=event.target.closest('[data-unit]');if(!unit||composer.visible||!tools.hidden)return;
    hoverUnit=unit.dataset.unit;const rect=unit.getBoundingClientRect(),b=$('object-annotate');b.hidden=false;
    b.style.top=Math.max(document.querySelector('.readerbar').getBoundingClientRect().bottom+4,rect.top)+'px';b.style.left=Math.max(5,Math.min(innerWidth-b.offsetWidth-8,rect.right-80))+'px';
  });
  $('object-annotate').addEventListener('click',()=>{if(hoverUnit)composer.open({source:{revision_id:reader.dataset.revision,created_view:core.view,source_language:'shared',kind:'object',segments:[{unit_id:hoverUnit}]}});});
  for(const el of article.querySelectorAll('[data-unit]'))el.tabIndex=0;
  article.addEventListener('keydown',e=>{if(e.altKey&&e.key.toLowerCase()==='a'&&!e.isComposing){const unit=e.target.closest('[data-unit]');if(unit){e.preventDefault();hoverUnit=unit.dataset.unit;$('object-annotate').click();}}});
  document.addEventListener('gareader:pdf-page-note',e=>composer.open({source:{revision_id:reader.dataset.revision,created_view:'pdf',source_language:'und',kind:'pdf_page',pdf_sha256:core.manifest.pdf_sha256,coordinate_system:'pdf-user-space',segments:[{page_index:e.detail.page_index}]}}));
  $('inline-toggle').addEventListener('click',()=>{if(!composer.composing)setInline(!inline);});
  $('annotations-toggle').addEventListener('click',()=>{if(composer.composing||composer.busy)return;composer.close();overview.hidden=false;floating.hidden=true;picker.hidden=true;$('annotations-toggle').setAttribute('aria-expanded','true');render();});
  $('annotations-close').addEventListener('click',()=>{closeOverview();render();$('annotations-toggle').focus({preventScroll:true});});
  $('inline-close').addEventListener('click',()=>{if(active)collapsed.add(active);active=null;focus=null;floating.hidden=true;$('focus-clear').hidden=true;render();});
  $('focus-clear').addEventListener('click',()=>{focus=null;active=null;$('focus-clear').hidden=true;render();});
  document.addEventListener('keydown',event=>{
    if(event.key!=='Escape'||event.isComposing||composer.composing)return;
    if(!tools.hidden){tools.hidden=true;return;}if(!picker.hidden){picker.hidden=true;return;}
    if(composer.visible){composer.close();return;}if(!overview.hidden){closeOverview();render();return;}
    if(!floating.hidden||active){$('inline-close').click();return;}
  });
  window.addEventListener('scroll',()=>{tools.hidden=true;$('object-annotate').hidden=true;},{passive:true});
  window.addEventListener('resize',()=>{tools.hidden=true;render();});
  document.addEventListener('gareader:view',()=>{tools.hidden=true;$('object-annotate').hidden=true;composer.save();cursor=null;focus=null;$('focus-clear').hidden=true;for(const note of notes.values())note.projections=[];if(initialized)refresh({full:true});render();});
  setInterval(()=>{if(!document.hidden&&initialized)refresh();},25000);
  document.addEventListener('visibilitychange',()=>{if(!document.hidden&&initialized)refresh();});
  composer.configure({beforeOpen(){closeOverview();tools.hidden=true;$('object-annotate').hidden=true;picker.hidden=true;},changed:render,
    async saved(id){active=id;single=true;collapsed.delete(id);await refresh({thread:id});core.announce(inline?'已保存这条批注。':'已保存，页内显示仍关闭。');render();requestAnimationFrame(()=>{if(composer.visible)return;const el=document.querySelector(`.annotation-card[data-thread="${id}"]`);el?.focus({preventScroll:true});});},
    async latest(thread,item){await refresh({thread});const root=notes.get(thread),found=root?.id===item?root:root?.replies.find(r=>r.id===item);return found?{...found,source:root.source}:null;}});
  geometry.configure({notes:()=>notes,inline:()=>inline,active:()=>active,activeSegment:()=>activeSegment,focus:()=>focus,layout:surfaceLayout,choose});
  setInline(inline);
  core.ready.then(async()=>{initialized=true;await refresh({full:true});
    await navigation.start({active:()=>active,async source(id,index,isCurrent){await refresh({full:true});if(!isCurrent())return false;const note=notes.get(id);if(!note?.source){core.announce('来源讨论已不可访问。');return false;}if(index>=note.source.segments.length){core.announce('来源片段不存在。');return false;}return await locate(note,{segment:index,isCurrent});},
      async restore(id,enabled){setInline(enabled);active=id&&notes.has(id)?id:null;single=!!active;focus=null;await refresh({full:true});render();}});
    if(location.hash==='#annotations')$('annotations-toggle').click();
  });
  window.GAReaderAnnotations={refresh,openEditor:composer.open,setInline,locate,get notes(){return notes;},get selection(){return selection;},get editor(){return composer.editor;},paintGeometry:geometry.paint};
})();

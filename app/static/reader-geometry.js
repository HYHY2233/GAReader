'use strict';
(() => {
  const core=window.GAReader;if(!core?.manifest)return;
  const $=id=>document.getElementById(id),overlay=$('annotation-overlays'),markers=$('annotation-markers'),svg=$('annotation-connectors');
  const repElements=new Map([...core.article.querySelectorAll('[data-representation]')].map(el=>[el.dataset.representation,el]));
  const maps=new WeakMap();let state={},frame=0,hits=[],lastTargets=[];
  function context(){return {revision:core.reader.dataset.revision,view:core.view,pdfHash:core.manifest.pdf_sha256,
    units:new Set(Object.keys(core.manifest.units)),representations:new Set([...repElements].filter(([,el])=>core.view==='both'||el.dataset.repLanguage===core.view).map(([id])=>id))};}
  const plan=note=>GAAnnotationDisplay.build(note,context());
  function rangeFor(p){
    const el=repElements.get(p.representation_id);if(!el?.getClientRects().length)return null;
    if(!maps.has(el))maps.set(el,GAReaderText.logical(el));const map=maps.get(el);
    if(map.chars.slice(p.start,p.end).join('')!==p.quote)return null;
    return GAReaderText.restore(map,p.start,p.end);
  }
  function rectsFor(p){
    if(core.view==='pdf')return window.GAReaderPDF?.projectedRects(p)||[];
    if(['exact','aligned_exact'].includes(p.precision)){const range=rangeFor(p);return range?[...range.getClientRects()]:[];}
    const unit=document.getElementById(p.unit_id);if(!unit?.getClientRects().length)return [];
    const pieces=p.language&&p.language!=='shared'?[...unit.querySelectorAll('[data-rep-language]')].filter(x=>x.dataset.repLanguage===p.language&&x.getClientRects().length):[];
    return (pieces.length?pieces:[unit]).map(x=>x.getBoundingClientRect());
  }
  function sourcePlan(source){
    if(!source||source.revision_id!==core.reader.dataset.revision)return [];
    const projections=source.segments.map((s,index)=>({...s,source_segment_index:index,
      precision:source.kind==='object'?'object':source.kind==='pdf_page'?'page':'exact',language:source.source_language}));
    return plan({id:'composer',source,projections});
  }
  const forSegment=(note,index)=>plan(note).filter(t=>t.source_segment_index===index).map(t=>t.projection);
  function clearPaint(){
    hits=[];lastTargets=[];overlay.replaceChildren();markers.replaceChildren();svg.replaceChildren();
    if(window.CSS?.highlights)for(const name of ['annotations','annotation-active','annotation-focus','annotation-compose'])CSS.highlights.delete(name);
  }
  function paint(){
    frame=0;hits=[];lastTargets=[];
    const visible=state.inline?.(),focus=state.focus?.(),draft=window.GAReaderComposer?.visible?window.GAReaderComposer.editor?.source:null;
    const top=document.querySelector('.readerbar').getBoundingClientRect().bottom+2;
    const notes=state.notes?.()||new Map(),positions=new Map(),groups=new Map(),shapes=[],highlights={annotations:[], 'annotation-active':[], 'annotation-focus':[], 'annotation-compose':[]};
    const clip=core.view==='pdf'?$('pdf-reader').getBoundingClientRect():core.article.getBoundingClientRect();let hasTargets=false;
    const clipped=r=>({left:Math.max(clip.left,r.left),right:Math.min(clip.right,r.right),top:r.top,bottom:r.bottom,width:Math.min(clip.right,r.right)-Math.max(clip.left,r.left),height:r.height});
    function add(target,kind){
      const p=target.projection,id=target.thread_id;if(!GAAnnotationDisplay.drawable(p))return null;
      const all=rectsFor(p).filter(r=>r.width>0&&r.height>0).map(clipped).filter(r=>r.width>0);
      const rects=all.filter(r=>r.bottom>top&&r.top<innerHeight-12),record={...target,rects};
      if(all.length&&id!=='composer')hasTargets=true;
      if(core.view!=='pdf'&&['exact','aligned_exact'].includes(p.precision)){const range=rangeFor(p);if(range)highlights[kind].push(range);}
      if(id!=='composer'&&rects.length){
        if(!positions.has(id))positions.set(id,[]);positions.get(id).push(record);lastTargets.push(record);
        for(const rect of rects)hits.push({...target,rect,id});
        const first=rects[0],key=core.view==='pdf'?`pdf:${p.page_index}:${Math.round(first.top/24)}`:`unit:${p.unit_id}`;
        if(!groups.has(key))groups.set(key,{rect:first,targets:new Map(),precision:p.precision});
        const group=groups.get(key);if(!group.targets.has(id))group.targets.set(id,target.source_segment_index);
      }
      for(const rect of rects){
        if(core.view!=='pdf'&&['exact','aligned_exact'].includes(p.precision)&&window.CSS?.highlights&&window.Highlight)continue;
        shapes.push({rect,precision:p.precision,kind,id});
      }
      return record;
    }
    if(visible)for(const note of notes.values())for(const target of plan(note))add(target,note.id===state.active?.()?'annotation-active':'annotations');
    if(focus&&notes.has(focus.id))for(const target of plan(notes.get(focus.id)).filter(t=>t.source_segment_index===focus.segment))add(target,'annotation-focus');
    const editor=window.GAReaderComposer?.editor;
    const draftPlan=draft&&editor?.thread&&notes.has(editor.thread)?plan(notes.get(editor.thread)).map(t=>({...t,thread_id:'composer'})):sourcePlan(draft);
    const draftTargets=draftPlan.map(t=>add(t,'annotation-compose')).filter(t=>t?.rects.length);
    const layout=state.layout?.(positions,draftTargets,{hasTargets})||{cards:[]};
    // Changing the reserved gutter changes line wrapping. Never publish pre-change geometry.
    if(layout.changed){clearPaint();schedule();return;}
    if(window.CSS?.highlights&&window.Highlight)for(const [name,ranges] of Object.entries(highlights)){CSS.highlights.delete(name);if(ranges.length)CSS.highlights.set(name,new Highlight(...ranges));}
    const fragment=document.createDocumentFragment();
    for(const item of shapes){const el=core.node('div',undefined,'annotation-geometry '+item.precision+' '+item.kind);Object.assign(el.style,{left:item.rect.left+'px',top:item.rect.top+'px',width:item.rect.width+'px',height:item.rect.height+'px'});fragment.append(el);}
    overlay.replaceChildren(fragment);
    const keep=new Set(),placed=[];
    if(visible&&!window.GAReaderComposer?.visible)for(const [key,group] of [...groups].sort((a,b)=>a[1].rect.top-b[1].rect.top||a[0].localeCompare(b[0]))){
      keep.add(key);let button=[...markers.children].find(b=>b.dataset.group===key);
      if(!button){button=core.node('button');button.type='button';button.className='annotation-marker';button.dataset.group=key;button.addEventListener('click',()=>state.choose?.(button._threads,button,button._segments));markers.append(button);}
      button._threads=[...group.targets.keys()];button._segments=Object.fromEntries(group.targets);button.textContent=group.targets.size;
      button.setAttribute('aria-label',`${group.targets.size} 条批注 · ${GAAnnotationPresentation.precision[group.precision]}`);
      button.classList.toggle('active',group.targets.has(state.active?.()));
      let y=Math.max(top+4,group.rect.top);for(const used of placed)if(Math.abs(y-used)<30)y=used+30;placed.push(y);
      Object.assign(button.style,{left:Math.min(innerWidth-34,Math.max(4,clip.right+5))+'px',top:y+'px'});
    }
    for(const button of [...markers.children])if(!keep.has(button.dataset.group))button.remove();
    const lines=document.createDocumentFragment();
    for(const {id,element} of layout.cards){
      if(id!=='composer'&&id!==state.active?.())continue;
      const targets=id==='composer'?draftTargets:positions.get(id);
      if(!targets?.length||!element.getClientRects().length)continue;
      const target=targets.find(t=>t.source_segment_index===state.activeSegment?.())||targets[0];
      const r=target.rects.at(-1),card=element.getBoundingClientRect(),p=target.projection;
      if(!r||card.left<clip.right+8||card.bottom<top||card.top>innerHeight)continue;
      const x=r.right,y=r.bottom+2,edge=clip.right+10,targetY=Math.max(card.top+18,Math.min(card.bottom-18,y));
      // A left bilingual column has no safe short path through its neighbour. Keep
      // its exact highlight and linked marker instead of drawing a large U-shaped line.
      const el=repElements.get(p.representation_id)||document.getElementById(p.unit_id),pair=el?.closest('.pair')||el?.querySelector('.pair');
      const columns=pair?[...pair.querySelectorAll(':scope > .en,:scope > .zh')].filter(e=>e.getClientRects().length).map(e=>e.getBoundingClientRect()):[];
      if(columns.some(c=>c.left>x+2&&c.top<y&&c.bottom>y))continue;
      if(Math.abs(y-targetY)>100)continue;
      const line=document.createElementNS('http://www.w3.org/2000/svg','path');line.setAttribute('d',`M ${x} ${y} H ${edge} V ${targetY} H ${card.left}`);
      Object.assign(line.dataset,{thread:id,segment:String(target.source_segment_index),precision:target.precision,sourceX:x,sourceY:y});
      line.classList.toggle('mapped',['block','page','object'].includes(target.precision));line.classList.add('active');lines.append(line);
    }
    svg.setAttribute('viewBox',`0 0 ${innerWidth} ${innerHeight}`);svg.replaceChildren(lines);
  }
  function schedule(){if(!frame)frame=requestAnimationFrame(paint);}
  for(const event of ['gareader:layout','gareader:pdf-rendered','gareader:composer'])document.addEventListener(event,schedule);
  window.addEventListener('scroll',schedule,{passive:true});document.addEventListener('scroll',schedule,{passive:true,capture:true});window.addEventListener('resize',schedule);
  window.visualViewport?.addEventListener('resize',schedule);core.article.addEventListener('load',schedule,true);document.fonts?.ready.then(schedule);
  const observer=window.ResizeObserver?new ResizeObserver(schedule):null;observer?.observe(core.article);
  window.GAReaderGeometry={configure(value){state=value;schedule();},schedule,paint,rangeFor,rectsFor,forSegment,plan,sourcePlan,context,
    get targets(){return lastTargets;},observe(element){observer?.observe(element);},unobserve(element){observer?.unobserve(element);},
    hitTargets(x,y){return hits.filter(h=>x>=h.rect.left&&x<=h.rect.right&&y>=h.rect.top&&y<=h.rect.bottom);},
    at(x,y){return [...new Set(this.hitTargets(x,y).map(h=>h.id))];}};
})();

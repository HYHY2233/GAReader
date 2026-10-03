'use strict';
(() => {
  const core=window.GAReader;if(!core?.manifest)return;
  const $=id=>document.getElementById(id),overlay=$('annotation-overlays'),markers=$('annotation-markers'),svg=$('annotation-connectors');
  const repElements=new Map([...core.article.querySelectorAll('[data-representation]')].map(el=>[el.dataset.representation,el]));
  const maps=new WeakMap();let state={},frame=0,hits=[];
  function rangeFor(p){
    const el=repElements.get(p.representation_id);if(!el?.getClientRects().length)return null;
    if(!maps.has(el))maps.set(el,GAReaderText.logical(el));const map=maps.get(el);
    if(map.chars.slice(p.start,p.end).join('')!==p.quote)return null;
    return GAReaderText.restore(map,p.start,p.end);
  }
  function rectsFor(p){
    if(core.view==='pdf')return window.GAReaderPDF?.projectedRects(p)||[];
    if(p.precision==='exact'||p.precision==='aligned_exact'){const range=rangeFor(p);return range?[...range.getClientRects()]:[];}
    const unit=document.getElementById(p.unit_id);if(!unit?.getClientRects().length)return [];
    const pieces=p.language&&p.language!=='shared'?[...unit.querySelectorAll('[data-rep-language]')].filter(x=>x.dataset.repLanguage===p.language&&x.getClientRects().length):[];
    return (pieces.length?pieces:[unit]).map(x=>x.getBoundingClientRect());
  }
  function sourceProjections(source){
    if(!source||source.revision_id!==core.reader.dataset.revision)return [];
    if(source.created_view==='pdf')return core.view==='pdf'?source.segments.map(s=>({...s,precision:source.kind==='pdf_text'?'exact':'page'})):[];
    if(core.view==='pdf')return [];
    return source.segments.map(s=>({...s,precision:source.kind==='object'?'object':'exact',language:source.source_language}));
  }
  function forSegment(note,index){
    const segment=note.source?.segments[index];if(!segment)return [];
    return note.projections.filter(p=>segment.page_index!==undefined?p.page_index===segment.page_index:
      segment.representation_id?p.representation_id===segment.representation_id:p.unit_id===segment.unit_id);
  }
  const drawable=p=>!['stale','unmapped'].includes(p.precision);
  function paint(){
    frame=0;hits=[];
    const visible=state.inline?.(),focus=state.focus?.(),draft=window.GAReaderComposer?.visible?window.GAReaderComposer.editor?.source:null;
    const top=document.querySelector('.readerbar').getBoundingClientRect().bottom+2;
    const notes=state.notes?.()||new Map(),positions=new Map(),groups=new Map(),geometry=[],highlights={annotations:[], 'annotation-active':[], 'annotation-focus':[], 'annotation-compose':[]};
    const bodyBounds=core.article.getBoundingClientRect(),clip=core.view==='pdf'?$('pdf-reader').getBoundingClientRect():bodyBounds;
    const clipped=r=>({left:Math.max(clip.left,r.left),right:Math.min(clip.right,r.right),top:r.top,bottom:r.bottom,width:Math.min(clip.right,r.right)-Math.max(clip.left,r.left),height:r.height});
    function add(id,projection,kind){
      if(!drawable(projection))return;
      const rects=rectsFor(projection).filter(r=>r.width>0&&r.height>0).map(clipped).filter(r=>r.width>0);
      const onScreen=rects.filter(r=>r.bottom>top&&r.top<innerHeight-12);
      if(core.view!=='pdf'&&['exact','aligned_exact'].includes(projection.precision)){
        const range=rangeFor(projection);if(range)highlights[kind].push(range);
      }
      if(id&&onScreen.length){
        if(!positions.has(id))positions.set(id,[]);positions.get(id).push(...onScreen);
        for(const rect of onScreen)hits.push({id,rect});
        const first=onScreen[0],key=core.view==='pdf'?`pdf:${projection.page_index}:${Math.round(first.top/24)}`:`${projection.unit_id}:${projection.language}`;
        if(!groups.has(key))groups.set(key,{rect:first,ids:new Set(),precision:projection.precision});groups.get(key).ids.add(id);
      }
      for(const rect of onScreen){
        if(core.view!=='pdf'&&['exact','aligned_exact'].includes(projection.precision)&&window.CSS?.highlights&&window.Highlight)continue;
        geometry.push({rect,precision:projection.precision,kind,id});
      }
    }
    if(visible)for(const note of notes.values())for(const p of note.projections)add(note.id,p,note.id===state.active?.()?'annotation-active':'annotations');
    if(focus&&notes.has(focus.id))for(const p of forSegment(notes.get(focus.id),focus.segment))add(focus.id,p,'annotation-focus');
    if(draft)for(const p of sourceProjections(draft))add(null,p,'annotation-compose');
    if(window.CSS?.highlights&&window.Highlight)for(const [name,ranges] of Object.entries(highlights)){CSS.highlights.delete(name);if(ranges.length)CSS.highlights.set(name,new Highlight(...ranges));}
    const shapes=document.createDocumentFragment();
    for(const item of geometry){const mark=core.node('div',undefined,'annotation-geometry '+item.precision+' '+item.kind);Object.assign(mark.style,{left:item.rect.left+'px',top:item.rect.top+'px',width:item.rect.width+'px',height:item.rect.height+'px'});shapes.append(mark);}
    overlay.replaceChildren(shapes);
    const keep=new Set();
    if(visible&&!window.GAReaderComposer?.visible)for(const [key,group] of groups){
      keep.add(key);let button=[...markers.children].find(b=>b.dataset.group===key);
      if(!button){button=core.node('button');button.type='button';button.className='annotation-marker';button.dataset.group=key;button.addEventListener('click',()=>state.choose?.(button._threads,button));markers.append(button);}
      button._threads=[...group.ids];button.textContent=group.ids.size;button.setAttribute('aria-label',`${group.ids.size} 条批注 · ${GAAnnotationPresentation.precision[group.precision]}`);
      Object.assign(button.style,{left:Math.min(innerWidth-34,Math.max(4,clip.right+5))+'px',top:Math.max(top+4,group.rect.top)+'px'});
    }
    for(const button of [...markers.children])if(!keep.has(button.dataset.group))button.remove();
    const draftRects=sourceProjections(draft).flatMap(rectsFor).filter(r=>r.bottom>top&&r.top<innerHeight);
    const cards=state.layout?.(positions,draftRects)||[];
    const lines=document.createDocumentFragment();
    for(const {id,element} of cards){
      const rects=id==='composer'?draftRects:positions.get(id);
      if(!rects?.length||!element.getClientRects().length)continue;
      const r=rects.at(-1),card=element.getBoundingClientRect();
      // Floating/mobile cards have no safe outside gutter, so keep the exact highlight without a crossing line.
      if(card.left<clip.right+8||card.bottom<top||card.top>innerHeight)continue;
      const x=r.right,y=r.bottom+2,edge=clip.right+10,targetY=Math.max(card.top+18,Math.min(card.bottom-18,y));
      const line=document.createElementNS('http://www.w3.org/2000/svg','path');
      // A left bilingual column routes through its inter-column gap, then below the pair.
      // It must not cross the neighbouring translation's glyphs.
      const source=id==='composer'?draft:notes.get(id)?.source;
      const rep=source?.segments.at(-1)?.representation_id,el=repElements.get(rep),pair=el?.closest('.pair');
      const en=pair?.querySelector(':scope > .en')?.getBoundingClientRect(),zh=pair?.querySelector(':scope > .zh')?.getBoundingClientRect();
      let route=`M ${x} ${y} H ${edge}`;
      if(en&&zh&&zh.left>en.right&&x<=en.right+2){const gutter=(en.right+zh.left)/2,bottom=pair.getBoundingClientRect().bottom+5;if(bottom>=innerHeight)continue;route=`M ${x} ${y} H ${gutter} V ${bottom} H ${edge}`;}
      line.setAttribute('d',route+` V ${targetY} H ${card.left}`);
      line.dataset.thread=id;line.dataset.sourceX=x;line.dataset.sourceY=y;
      const note=notes.get(id),block=note?.projections.some(p=>['block','page','object'].includes(p.precision));
      line.classList.toggle('mapped',!!block);line.classList.toggle('active',id===state.active?.()||id==='composer');lines.append(line);
    }
    svg.setAttribute('viewBox',`0 0 ${innerWidth} ${innerHeight}`);svg.replaceChildren(lines);
  }
  function schedule(){if(!frame)frame=requestAnimationFrame(paint);}
  for(const event of ['gareader:layout','gareader:pdf-rendered','gareader:composer'])document.addEventListener(event,schedule);
  window.addEventListener('scroll',schedule,{passive:true});window.addEventListener('resize',schedule);
  window.visualViewport?.addEventListener('resize',schedule);
  core.article.addEventListener('load',schedule,true);document.fonts?.ready.then(schedule);
  const observer=window.ResizeObserver?new ResizeObserver(schedule):null;observer?.observe(core.article);
  window.GAReaderGeometry={configure(value){state=value;schedule();},schedule,paint,rangeFor,rectsFor,forSegment,
    observe(element){observer?.observe(element);},unobserve(element){observer?.unobserve(element);},
    at(x,y){return [...new Set(hits.filter(h=>x>=h.rect.left&&x<=h.rect.right&&y>=h.rect.top&&y<=h.rect.bottom).map(h=>h.id))];}};
})();

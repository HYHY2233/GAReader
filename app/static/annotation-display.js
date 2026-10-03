'use strict';
// A projection is a candidate. Only this plan decides which candidates are displayed.
((root) => {
  const exact = p => ['exact','aligned_exact'].includes(p.precision);
  const drawable = p => !['unmapped','stale'].includes(p.precision);
  function stable(value) {
    if(Array.isArray(value))return '['+value.map(stable).join(',')+']';
    if(value&&typeof value==='object')return '{'+Object.keys(value).sort().map(k=>JSON.stringify(k)+':'+stable(value[k])).join(',')+'}';
    return JSON.stringify(value);
  }
  function build(note, context) {
    if(!note.source)return [];
    const source=note.source, result=[];
    source.segments.forEach((segment,index)=>{
      const all=(note.projections||[]).filter(p=>p.source_segment_index===index ||
        (p.source_segment_index===undefined&&source.segments.length===1&&index===0));
      const visible=all.filter(p=>drawable(p)&&(context.view==='pdf'
        ? Number.isInteger(p.page_index)
        : p.unit_id&&context.units.has(p.unit_id)&&(!p.language||p.language==='shared'||context.view==='both'||p.language===context.view)&&
          (!p.representation_id||context.representations.has(p.representation_id))));
      const rank=p=>{
        if(exact(p)){
          const original=source.revision_id===context.revision && (context.view==='pdf'
            ? source.created_view==='pdf'&&source.pdf_sha256===context.pdfHash&&p.page_index===segment.page_index
            : source.created_view!=='pdf'&&p.representation_id===segment.representation_id);
          return original?0:p.precision==='exact'?1:2;
        }
        return {object:3,block:4,page:5}[p.precision]??6;
      };
      // Rank per source segment, never globally across a multi-segment discussion.
      const best=visible.length?Math.min(...visible.map(rank)):Infinity;
      let selected=visible.filter(p=>rank(p)===best);
      if(!selected.length)selected=all.filter(p=>!drawable(p)).sort((a,b)=>stable(a).localeCompare(stable(b))).slice(0,1);
      // Several verified units/pages can belong to one segment. Keep their coverage,
      // but choose one language for each HTML unit instead of duplicating a marker.
      const preferred=source.source_language==='zh'?'zh':'en', groups=new Map();
      for(const p of selected){
        const key=context.view==='pdf'?stable([p.page_index,p.quads||[],p.precision]):stable([p.unit_id,p.start,p.end,p.precision]);
        const old=groups.get(key),score=q=>(q.language===preferred?0:q.language==='shared'?1:2)+':'+stable(q);
        if(!old||score(p)<score(old))groups.set(key,p);
      }
      const ordered=[...groups.values()].sort((a,b)=>(a.page_index??0)-(b.page_index??0)||String(a.unit_id||'').localeCompare(String(b.unit_id||''))||(a.start??0)-(b.start??0)||stable(a).localeCompare(stable(b)));
      for(const projection of ordered)result.push({thread_id:note.id,source_segment_index:index,projection,
        precision:projection.precision,key:index+':'+stable(projection)});
    });
    return result;
  }
  const api={build,drawable};root.GAAnnotationDisplay=api;
  if(typeof module!=='undefined')module.exports=api;
})(typeof window==='undefined'?globalThis:window);

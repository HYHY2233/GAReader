'use strict';
(() => {
  const core=window.GAReader;if(!core)return;
  const $=id=>document.getElementById(id);
  const container=$('pdf-reader'),pagesRoot=$('pdf-pages'),reader=core.reader;
  const pages=new Map();let pdfjs,documentPDF,loading,observer,scale=1,rotation=0,fit='width',generation=0,jumpEpoch=0;
  const base=`/api/papers/${reader.dataset.paper}/revisions/${reader.dataset.revision}/pdf/`;
  function status(text){$('pdf-status').textContent=text;}
  function currentPage(){
    const top=document.querySelector('.readerbar').getBoundingClientRect().bottom;
    for(const [index,info] of pages)if(info.section.getBoundingClientRect().bottom>top)return index;
    return 0;
  }
  function viewport(info){return info.page.getViewport({scale,rotation:(info.page.rotate+rotation)%360});}
  function fitScale(){
    const first=pages.values().next().value;if(!first)return;
    const natural=first.page.getViewport({scale:1,rotation:(first.page.rotate+rotation)%360});
    const available=Math.max(180,(container.clientWidth||container.parentElement.clientWidth)-28);
    scale=Math.min(3,available/natural.width);
    if(fit==='page')scale=Math.min(scale,Math.max(200,innerHeight-document.querySelector('.readerbar').offsetHeight-85)/natural.height);
    scale=Math.max(.1,scale);$('pdf-scale').value=Math.round(scale*100);
  }
  function dimensions(info){
    info.viewport=viewport(info);info.surface.style.width=info.viewport.width+'px';info.surface.style.height=info.viewport.height+'px';
    info.surface.style.setProperty('--total-scale-factor',scale);
    info.surface.style.setProperty('--scale-factor',scale);
    info.surface.style.setProperty('--scale-round-x','1px');info.surface.style.setProperty('--scale-round-y','1px');
  }
  function renderPage(info){
    if(info.rendered===generation)return Promise.resolve();
    if(info.rendering===generation&&info.renderPromise)return info.renderPromise;
    const work=renderPageWork(info);info.renderPromise=work;return work;
  }
  async function renderPageWork(info){
    const token=generation;info.rendering=token;
    try {
      if(info.task){info.task.cancel();try{await info.task.promise;}catch{}}
      info.textTask?.cancel();info.section.querySelector('.pdf-no-text')?.remove();info.surface.replaceChildren();dimensions(info);
      const canvas=document.createElement('canvas');canvas.setAttribute('aria-label',`原版 PDF 第 ${info.index+1} 页`);
      const ratio=Math.min(devicePixelRatio||1,2,Math.sqrt(16_000_000/(info.viewport.width*info.viewport.height)));
      canvas.width=Math.ceil(info.viewport.width*ratio);canvas.height=Math.ceil(info.viewport.height*ratio);
      canvas.style.width=info.viewport.width+'px';canvas.style.height=info.viewport.height+'px';
      const textLayer=document.createElement('div');textLayer.className='textLayer';textLayer.dataset.pageIndex=info.index;
      info.surface.append(canvas,textLayer);info.textLayer=textLayer;
      info.task=info.page.render({canvasContext:canvas.getContext('2d'),viewport:info.viewport,
        transform:ratio===1?null:[ratio,0,0,ratio,0,0],annotationMode:pdfjs.AnnotationMode.DISABLE});
      await info.task.promise;
      if(token!==generation)return;
      const content=await info.page.getTextContent({disableNormalization:true});
      info.textTask=new pdfjs.TextLayer({textContentSource:content,container:textLayer,viewport:info.viewport});
      await info.textTask.render();
      if(!content.items.some(item=>item.str?.trim())){
        const hint=document.createElement('span');hint.className='pdf-no-text';hint.textContent='此页没有可提取的文字，可使用整页批注。';info.section.append(hint);
      }
      info.rendered=token;document.dispatchEvent(new CustomEvent('gareader:pdf-rendered',{detail:{page_index:info.index}}));
    }catch(error){
      if(error.name!=='RenderingCancelledException'&&error.name!=='AbortException'){status('本页加载失败，可切换视图后重试。');console.error(error);}
    }finally{if(info.rendering===token)info.rendering=null;}
  }
  async function load(){
    if(loading)return loading;
    if(documentPDF)return documentPDF;
    loading=(async()=>{
      status('正在加载原版 PDF…');$('pdf-retry').hidden=true;
      pdfjs=await import(reader.dataset.pdfLibrary);pdfjs.GlobalWorkerOptions.workerSrc=reader.dataset.pdfWorker;
      const response=await fetch(base,{credentials:'same-origin'});
      if(!response.ok){let detail;try{detail=await response.json();}catch{}throw Error(response.status===401?'登录已失效，请重新登录后读取原版 PDF。':detail?.error||'原版 PDF 无法读取，请确认文件后重试。');}
      const bytes=await response.arrayBuffer();
      const sha=[...new Uint8Array(await crypto.subtle.digest('SHA-256',bytes))].map(x=>x.toString(16).padStart(2,'0')).join('');
      if(sha!==core.manifest?.pdf_sha256)throw Error('PDF 来源校验失败，未使用旧坐标。');
      const assets=reader.dataset.pdfAssets;
      documentPDF=await pdfjs.getDocument({data:new Uint8Array(bytes),cMapUrl:assets+'cmaps/',cMapPacked:true,
        standardFontDataUrl:assets+'standard_fonts/',wasmUrl:assets+'wasm/',isEvalSupported:false,
        enableXfa:false,disableRange:true,disableAutoFetch:true,stopAtErrors:false}).promise;
      pagesRoot.replaceChildren();pages.clear();observer?.disconnect();
      for(let index=0;index<documentPDF.numPages;index++){
        const page=await documentPDF.getPage(index+1),section=document.createElement('section');
        section.className='pdf-page';section.dataset.pdfPage=index;
        const header=document.createElement('header');header.className='pdf-page-label';header.dataset.readerControl='true';
        const label=core.manifest?.pdf.pages[index]?.page_label;
        const name=document.createElement('span');name.textContent=`PDF 文件第 ${index+1} 页`+(label&&label!==String(index+1)?`（文内标签 ${label}）`:'');
        const add=document.createElement('button');add.textContent='＋ 整页批注';add.type='button';
        add.addEventListener('click',()=>document.dispatchEvent(new CustomEvent('gareader:pdf-page-note',{detail:{page_index:index}})));
        header.append(name,add);
        const surface=document.createElement('div');surface.className='pdf-surface';surface.dataset.pageIndex=index;
        section.append(header,surface);pagesRoot.append(section);
        pages.set(index,{index,page,section,surface,rendered:-1,rendering:null});
      }
      fitScale();for(const info of pages.values())dimensions(info);
      observer=new IntersectionObserver(entries=>{for(const entry of entries)if(entry.isIntersecting&&core.view==='pdf')renderPage(pages.get(Number(entry.target.dataset.pdfPage)));},{rootMargin:'900px 0px'});
      for(const info of pages.values())observer.observe(info.section);
      $('pdf-page-total').textContent='/ '+documentPDF.numPages;$('pdf-page-number').max=documentPDF.numPages;
      const target=Math.min(documentPDF.numPages-1,core.position.pdf_page||0);
      await renderPage(pages.get(target));$('pdf-page-number').value=target+1;
      status('原版 PDF · '+documentPDF.numPages+' 页');return documentPDF;
    })().catch(error=>{status(error.message||'PDF 加载失败。');$('pdf-retry').hidden=false;loading=null;documentPDF=null;throw error;});
    return loading;
  }
  async function jump(index,{scroll=true,isCurrent=()=>core.view==='pdf'}={}){
    const epoch=++jumpEpoch;
    const info=pages.get(Math.max(0,Math.min((documentPDF?.numPages||1)-1,index)));if(!info)return;
    await renderPage(info);if(!isCurrent()||epoch!==jumpEpoch)return;$('pdf-page-number').value=info.index+1;
    if(scroll)info.section.scrollIntoView({block:'start',behavior:'instant'});
    core.emitLayout();
  }
  async function rerender(){
    if(!documentPDF)return;
    const selected=currentPage();generation++;
    if(fit)fitScale();
    for(const info of pages.values()){
      info.task?.cancel();info.textTask?.cancel();info.surface.replaceChildren();info.rendered=-1;info.rendering=null;dimensions(info);
    }
    await jump(selected);
    for(const info of pages.values()){
      const rect=info.section.getBoundingClientRect();if(rect.bottom>-500&&rect.top<innerHeight+700)renderPage(info);
    }
    core.emitLayout();
  }
  function projectedRects(projection){
    const info=pages.get(projection.page_index);if(!info)return [];
    const bounds=info.surface.getBoundingClientRect();
    if(projection.precision==='page')return [{left:bounds.left,top:bounds.top,right:bounds.right,bottom:bounds.top+32,width:bounds.width,height:32}];
    return (projection.quads||[]).map(quad=>{
      const points=[];for(let i=0;i<quad.length;i+=2)points.push(info.viewport.convertToViewportPoint(quad[i],quad[i+1]));
      const left=bounds.left+Math.min(...points.map(p=>p[0])),right=bounds.left+Math.max(...points.map(p=>p[0]));
      const top=bounds.top+Math.min(...points.map(p=>p[1])),bottom=bounds.top+Math.max(...points.map(p=>p[1]));
      return {left,right,top,bottom,width:right-left,height:bottom-top};
    });
  }
  function sourceSelection(range){
    const segments=[];
    for(const info of pages.values()){
      if(!info.textLayer||!range.intersectsNode(info.textLayer))continue;
      const map=GAReaderText.logical(info.textLayer,{breaks:true}),selected=GAReaderText.selected(range,map);
      if(!selected)continue;
      const rect=info.surface.getBoundingClientRect();
      const quads=[...selected.range.getClientRects()].filter(r=>r.width>.1&&r.height>.1).map(r=>{
        const clipped={left:Math.max(r.left,rect.left),right:Math.min(r.right,rect.right),top:Math.max(r.top,rect.top),bottom:Math.min(r.bottom,rect.bottom)};
        if(clipped.left>=clipped.right||clipped.top>=clipped.bottom)return null;
        return [[clipped.left,clipped.top],[clipped.right,clipped.top],[clipped.right,clipped.bottom],[clipped.left,clipped.bottom]]
          .flatMap(([x,y])=>info.viewport.convertToPdfPoint(x-rect.left,y-rect.top));
      }).filter(Boolean);
      segments.push({page_index:info.index,quote:selected.quote,raw_quote:selected.raw_quote,quads});
    }
    if(!segments.length)throw Error('请在 PDF 文字层选择文字；扫描页可使用整页批注。');
    if(segments.length>32)throw Error('一次最多批注 32 个页面片段。');
    return {revision_id:reader.dataset.revision,created_view:'pdf',source_language:'en',kind:'pdf_text',
      pdf_sha256:core.manifest.pdf_sha256,coordinate_system:'pdf-user-space',segments};
  }
  async function locate(projection,{isCurrent=()=>core.view==='pdf'}={}){
    await load();if(!isCurrent())return;await jump(projection.page_index,{isCurrent});if(!isCurrent())return;
    const rect=projectedRects(projection)[0];if(!rect)return;
    const bounds=container.getBoundingClientRect();
    if(rect.left<bounds.left||rect.right>bounds.right)container.scrollLeft+=rect.left-bounds.left-45;
    const top=document.querySelector('.readerbar').getBoundingClientRect().bottom;
    window.scrollTo({top:scrollY+rect.top-top-65,behavior:'instant'});core.emitLayout();
  }
  function capturePosition(){
    const page=currentPage(),info=pages.get(page);if(!info)return {page};
    const bounds=info.surface.getBoundingClientRect(),top=document.querySelector('.readerbar').getBoundingClientRect().bottom+12;
    return {page,point:info.viewport.convertToPdfPoint(container.getBoundingClientRect().left-bounds.left,top-bounds.top),scale,rotation};
  }
  async function restorePosition(saved,{isCurrent=()=>core.view==='pdf'}={}){
    if(!saved)return;await load();if(!isCurrent())return;
    const index=Math.max(0,Math.min(pages.size-1,saved.page||0));
    scale=Math.max(.1,Math.min(3,saved.scale||scale));rotation=[0,90,180,270].includes(saved.rotation)?saved.rotation:rotation;fit=null;generation++;
    $('pdf-scale').value=Math.round(scale*100);
    for(const info of pages.values()){info.task?.cancel();info.textTask?.cancel();info.surface.replaceChildren();info.rendered=-1;info.rendering=null;dimensions(info);}
    await jump(index,{scroll:false,isCurrent});if(!isCurrent())return;
    const info=pages.get(index),bounds=info.surface.getBoundingClientRect(),point=saved.point?info.viewport.convertToViewportPoint(...saved.point):[0,0];
    container.scrollLeft+=bounds.left+point[0]-container.getBoundingClientRect().left;
    window.scrollTo({top:scrollY+bounds.top+point[1]-document.querySelector('.readerbar').getBoundingClientRect().bottom-12,behavior:'instant'});core.emitLayout();
  }
  window.GAReaderPDF={load,currentPage,jump,locate,projectedRects,sourceSelection,capturePosition,restorePosition,get pages(){return pages;},get scale(){return scale;},get rotation(){return rotation;}};
  document.addEventListener('gareader:view',()=>{jumpEpoch++;if(core.view==='pdf')load().then(()=>{if(core.view!=='pdf')return;for(const info of pages.values())if(info.section.getBoundingClientRect().top<innerHeight+900)renderPage(info);core.emitLayout();}).catch(()=>{});});
  $('pdf-retry').addEventListener('click',()=>load().catch(()=>{}));
  $('pdf-page-number').addEventListener('change',e=>{const page=Number(e.target.value);if(!Number.isInteger(page)||page<1||page>(documentPDF?.numPages||1)){status('请输入有效的物理页码。');e.target.value=currentPage()+1;return;}jump(page-1);});
  $('pdf-prev').addEventListener('click',()=>jump(currentPage()-1));$('pdf-next').addEventListener('click',()=>jump(currentPage()+1));
  $('pdf-scale').addEventListener('change',e=>{const n=Number(e.target.value);if(!Number.isFinite(n)){e.target.value=Math.round(scale*100);return;}scale=Math.max(.5,Math.min(3,n/100));e.target.value=Math.round(scale*100);fit=null;rerender();});
  for(const id of ['pdf-page-number','pdf-scale'])$(id).addEventListener('keydown',e=>{if(e.key==='Enter'){e.preventDefault();e.target.dispatchEvent(new Event('change'));}});
  $('pdf-fit-width').addEventListener('click',()=>{fit='width';rerender();});$('pdf-fit-page').addEventListener('click',()=>{fit='page';rerender();});
  $('pdf-rotate').addEventListener('click',()=>{rotation=(rotation+90)%360;status(`旋转 ${rotation}°`);rerender();});
  let resizeTimer;window.addEventListener('resize',()=>{if(core.view==='pdf'&&fit){clearTimeout(resizeTimer);resizeTimer=setTimeout(rerender,160);}});
  if(window.ResizeObserver){let width=0;new ResizeObserver(()=>{const next=container.clientWidth;if(next&&next!==width){width=next;if(core.view==='pdf'&&fit){clearTimeout(resizeTimer);resizeTimer=setTimeout(rerender,160);}}}).observe(container);}
  window.addEventListener('scroll',()=>{if(core.view==='pdf')$('pdf-page-number').value=currentPage()+1;},{passive:true});
  container.addEventListener('scroll',()=>core.emitLayout(),{passive:true});
  if(core.view==='pdf')load().catch(()=>{});
})();

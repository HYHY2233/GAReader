'use strict';
(() => {
 const reader=document.getElementById('reader'); if(!reader)return;
 history.scrollRestoration='manual';
 const article=document.getElementById('article'), panel=document.getElementById('panel');
 const apiBase=`/api/papers/${reader.dataset.paper}/`;
 const storageKey=`paper-reader:v1:${reader.dataset.user}:${reader.dataset.paper}:${reader.dataset.revision}`;
 let saved={}; try{saved=JSON.parse(localStorage.getItem(storageKey)||'{}');}catch{}
 const persist=()=>{try{localStorage.setItem(storageKey,JSON.stringify(saved));}catch{}};
 const titles={scores:'两项评分',comments:'全文评论',contents:'阅读目录',search:'文内查找',more:'论文信息'};
 const toolbar=document.querySelector('.readerbar');
 function measureToolbar(){document.documentElement.style.setProperty('--readerbar-height',Math.ceil(toolbar.getBoundingClientRect().height)+'px');}
 measureToolbar();window.addEventListener('resize',measureToolbar);
 if(window.ResizeObserver)new ResizeObserver(measureToolbar).observe(toolbar);
 let opener=null, activeSection='';
 const $=id=>document.getElementById(id);
 const node=(tag,text,cls)=>{const el=document.createElement(tag);if(text!==undefined)el.textContent=text;if(cls)el.className=cls;return el;};
 async function api(path,method='GET',data){
  const res=await fetch(apiBase+path,{method,headers:{'Content-Type':'application/json','X-CSRFToken':reader.dataset.csrf},...(data===undefined?{}:{body:JSON.stringify(data)})});
  let result;try{result=await res.json();}catch{throw Error('请求未保存，请刷新登录状态后重试。');}
  if(!res.ok)throw Error(result.error||'请求未保存，请稍后重试。');return result;
 }
 function closePanel(){panel.close();if(opener)opener.focus({preventScroll:true});}
 async function openPanel(kind,button){
  activeSection=kind;opener=button||document.querySelector(`[data-panel="${kind}"]`);
  $('panel-title').textContent=titles[kind];
  panel.querySelectorAll('[data-section]').forEach(s=>s.hidden=s.dataset.section!==kind);
  if(!panel.open)panel.showModal();
  if(kind==='scores')await loadRatings();
  if(kind==='comments')await loadComments();
  if(kind==='search')$('in-paper-search').focus();
 }
 document.querySelectorAll('[data-panel]').forEach(b=>b.addEventListener('click',()=>openPanel(b.dataset.panel,b)));
 panel.querySelector('[data-close]').addEventListener('click',closePanel);
 panel.addEventListener('click',e=>{if(e.target===panel&&e.clientX<panel.getBoundingClientRect().left)closePanel();});
 panel.addEventListener('close',()=>{if(opener)opener.focus({preventScroll:true});});
 const systemTheme=matchMedia('(prefers-color-scheme: dark)');
 function applySettings(){
  const theme=saved.theme||'auto', font=String(saved.font||18);
  document.documentElement.classList.toggle('dark',theme==='dark'||theme==='auto'&&systemTheme.matches);
  document.documentElement.classList.toggle('sepia',theme==='sepia');
  for(const size of [16,18,20,22])document.body.classList.toggle(`font-${size}`,font===String(size));
  document.body.classList.toggle('hide-sources',saved.sources===false);
  $('theme').value=theme;$('font-size').value=font;$('source-toggle').checked=saved.sources!==false;
 }
 applySettings();systemTheme.addEventListener('change',applySettings);
 $('theme').addEventListener('change',e=>{saved.theme=e.target.value;applySettings();persist();});
 $('font-size').addEventListener('change',e=>{saved.font=Number(e.target.value);applySettings();persist();});
 $('source-toggle').addEventListener('change',e=>{saved.sources=e.target.checked;applySettings();persist();});
 // Tables scroll locally even when the original markup did not provide a wrapper.
 article.querySelectorAll('table').forEach(t=>{const wrapper=node('div',undefined,'table-viewport');t.before(wrapper);wrapper.append(t);});
 // Keep the source's full front matter, collapsed by default.
 const sourceHeader=article.querySelector('main>header');
 if(sourceHeader){
  const details=node('details'), summary=node('summary','来源与译稿说明');details.append(summary);
  [...sourceHeader.children].filter(x=>!x.classList.contains('pair')).forEach(x=>details.append(x));sourceHeader.append(details);
 }
 const ammoniaMain=article.querySelector('main.paper');
 if(ammoniaMain){
  const title=ammoniaMain.firstElementChild,details=node('details');details.append(node('summary','来源与译稿说明'));
  let next=title.nextSibling;while(next&&!(next.nodeType===1&&next.classList.contains('heading-pair'))){const current=next;next=next.nextSibling;details.append(current);}
  title.after(details);
 }
 const nav=JSON.parse($('article-nav').textContent);
 for(const [kind,label] of Object.entries({sections:'章节',figures:'图片',tables:'表格',equations:'公式'})){
  const details=node('details');details.open=kind==='sections';details.append(node('summary',`${label} · ${nav[kind].length}`));
  nav[kind].forEach((item,i)=>{const a=node('a',`${kind==='sections'?'':(i+1)+'. '}${item.label}`);a.href='#'+item.id;a.addEventListener('click',()=>closePanel());details.append(a);});$('nav-list').append(details);
 }
 $('to-top').addEventListener('click',()=>window.scrollTo({top:0,behavior:'smooth'}));
 const imageDialog=$('image-dialog'), zoom=$('zoom-image');let zoomIndex=2;const zooms=[50,75,100,150,200];
 function applyZoom(){zoom.className='zoom-'+zooms[zoomIndex];$('zoom-label').textContent=zooms[zoomIndex]+'%';}
 article.querySelectorAll('img').forEach(im=>{im.tabIndex=0;im.setAttribute('role','button');im.setAttribute('aria-label','放大：'+im.alt);const open=()=>{opener=im;zoom.src=im.src;zoom.alt=im.alt;zoomIndex=2;applyZoom();imageDialog.showModal();};im.addEventListener('click',open);im.addEventListener('keydown',e=>{if(e.key==='Enter')open();});});
 $('zoom-in').addEventListener('click',()=>{zoomIndex=Math.min(4,zoomIndex+1);applyZoom();});
 $('zoom-out').addEventListener('click',()=>{zoomIndex=Math.max(0,zoomIndex-1);applyZoom();});
 $('image-close').addEventListener('click',()=>imageDialog.close());
 imageDialog.addEventListener('close',()=>opener?.focus({preventScroll:true}));
 let ranges=[],hit=-1,searchTimer;
 function highlight(){if(CSS.highlights){CSS.highlights.set('search-results',new Highlight(...ranges));CSS.highlights.set('search-active',new Highlight(...(hit>=0?[ranges[hit]]:[])));}}
 function find(){
  ranges=[];hit=-1;const query=$('in-paper-search').value.trim().toLocaleLowerCase();
  if(query){const walker=document.createTreeWalker(article,NodeFilter.SHOW_TEXT,{acceptNode:n=>n.parentElement.closest('annotation,script,style,summary')?NodeFilter.FILTER_REJECT:NodeFilter.FILTER_ACCEPT});let text;
   while((text=walker.nextNode())){const content=text.textContent.toLocaleLowerCase();let start=0,idx;while((idx=content.indexOf(query,start))>=0){const range=new Range();range.setStart(text,idx);range.setEnd(text,idx+query.length);ranges.push(range);start=idx+query.length;if(ranges.length>=3000)break;}if(ranges.length>=3000)break;}}
  highlight();$('search-status').textContent=query?`找到 ${ranges.length} 处${ranges.length===3000?'（最多显示 3000 处）':''}`:'输入关键词后按 Enter 定位。';
 }
 function jump(step){if(!ranges.length)return;hit=(hit+step+ranges.length)%ranges.length;highlight();const el=ranges[hit].startContainer.parentElement;let d=el.closest('details');while(d){d.open=true;d=d.parentElement.closest('details');}closePanel();el.scrollIntoView({block:'center'});$('search-status').textContent=`第 ${hit+1} / ${ranges.length} 处`;}
 $('in-paper-search').addEventListener('input',()=>{clearTimeout(searchTimer);searchTimer=setTimeout(find,150);});
 $('in-paper-search').addEventListener('keydown',e=>{if(e.key==='Enter'){clearTimeout(searchTimer);find();jump(1);}});
 $('search-next').addEventListener('click',()=>jump(1));$('search-prev').addEventListener('click',()=>jump(-1));
 $('search-clear').addEventListener('click',()=>{$('in-paper-search').value='';find();$('in-paper-search').focus();});
 const ratingHints={interesting:['兴趣较低','有一点启发','值得了解','很有启发','非常有意思'],importance:['背景资料','有参考价值','相关人员值得读','建议优先读','核心参考']};
 let ratingState={},ratingBusy=new Set();
 function paintRating(dim){
  let row=$('rating-'+dim);if(!row){row=node('div',undefined,'rating-row');row.id='rating-'+dim;$('rating-rows').append(row);}row.replaceChildren();
  const value=ratingState[dim];if(!value)return;
  row.append(node('h3',dim==='interesting'?'有意思':'重要性'));
  row.append(node('p',`${value.count?Number(value.average).toFixed(1)+' 分':'暂无评分'} · ${value.count} 人 · 我：${value.mine?value.mine+' 分':'未评分'}`,'rating-summary'));
  const buttons=node('div',undefined,'rating-buttons');
  ratingHints[dim].forEach((hint,i)=>{const b=node('button',String(i+1),value.mine===i+1?'selected':'');b.title=hint;b.setAttribute('aria-label',`${i+1} 分：${hint}`);b.setAttribute('aria-pressed',String(value.mine===i+1));b.disabled=ratingBusy.has(dim);b.addEventListener('click',()=>saveRating(dim,i+1));buttons.append(b);});row.append(buttons);
  row.append(node('small',value.mine?ratingHints[dim][value.mine-1]:'选择 1—5 分；悬停可查看各分值含义'));
  const undo=node('button','撤回这一项','undo');undo.disabled=ratingBusy.has(dim)||!value.mine;undo.addEventListener('click',()=>saveRating(dim,null));row.append(undo);
 }
 async function loadRatings(){try{const state=await api('ratings/');for(const dim of Object.keys(ratingHints)){if(!ratingBusy.has(dim)){ratingState[dim]=state[dim];paintRating(dim);}}}catch(e){$('rating-status').textContent=e.message||'加载失败，请重新打开评分。';}}
 async function saveRating(dim,value){if(ratingBusy.has(dim))return;ratingBusy.add(dim);paintRating(dim);$('rating-status').textContent='正在保存…';try{const res=await api(`ratings/${dim}/`,value===null?'DELETE':'PUT',value===null?{}:{value});ratingState[dim]=res[dim];$('rating-status').textContent='已保存';}catch(e){$('rating-status').textContent=e.message||'连接失败，未保存。';}finally{ratingBusy.delete(dim);paintRating(dim);}}
 let commentMode={parent:null,edit:null},requestKey=null,requestSignature='',commentRows=[];
 function resetComment(){commentMode={parent:null,edit:null};$('comment-body').value='';$('reply-state').textContent='';$('cancel-comment').hidden=true;requestKey=null;requestSignature='';$('comment-form').querySelector('.primary').textContent='发表评论';}
 function editComment(c,reply){commentMode={parent:reply?c.id:null,edit:reply?null:c.id};$('comment-body').value=reply?'':c.body;$('reply-state').textContent=reply?'回复 '+c.author:'编辑自己的评论';$('cancel-comment').hidden=false;$('comment-form').querySelector('.primary').textContent=reply?'发表回复':'保存修改';$('comment-body').focus();}
 async function loadComments(){try{const result=await api('comments/');commentRows=result.comments;$('comment-count').textContent=`${result.count} 条评论与回复`;$('comment-list').replaceChildren();for(const c of commentRows.filter(c=>!c.parent)){paintComment(c);for(const reply of commentRows.filter(r=>r.parent===c.id))paintComment(reply);}}catch(e){$('comment-status').textContent=e.message||'加载评论失败。';}}
 function paintComment(c){
  const block=node('article',undefined,'comment'+(c.parent?' reply':''));block.dataset.id=c.id;
  block.append(node('strong',c.author));block.append(node('small',c.created_at+(c.edited?' · 已编辑':'')));block.append(node('p',c.body===null?c.placeholder:c.body,'comment-body'));
  const actions=node('div',undefined,'actions');
  function action(text,fn){const b=node('button',text);b.addEventListener('click',async()=>{b.disabled=true;try{await fn();}catch(e){$('comment-status').textContent=e.message||'未保存，请稍后重试。';}finally{b.disabled=false;}});actions.append(b);}
  if(!c.parent&&c.body!==null)action('回复',()=>editComment(c,true));
  if(c.can_edit){action('编辑',()=>editComment(c,false));action('删除',async()=>{if(!confirm('删除这条评论？已有回复会保留。'))return;await api(`comments/${c.id}/`,'DELETE',{});await loadComments();});}
  if(c.can_hide)action(c.hidden?'恢复显示':'隐藏',async()=>{await api(`comments/${c.id}/hide/`,'POST',{hidden:!c.hidden});await loadComments();});
  block.append(actions);$('comment-list').append(block);
 }
 $('cancel-comment').addEventListener('click',resetComment);
 $('comment-form').addEventListener('submit',async e=>{e.preventDefault();const body=$('comment-body').value.trim();if(!body||body.length>5000)return;const button=e.target.querySelector('.primary');if(button.disabled)return;button.disabled=true;$('comment-status').textContent='正在保存…';
  try{if(commentMode.edit)await api(`comments/${commentMode.edit}/`,'PATCH',{body});else{const signature=JSON.stringify([commentMode.parent,body]);if(signature!==requestSignature){requestSignature=signature;requestKey=crypto.randomUUID();}await api('comments/','POST',{body,parent:commentMode.parent,request_key:requestKey});}resetComment();$('comment-status').textContent='已保存';await loadComments();}catch(err){$('comment-status').textContent=err.message||'连接失败，未保存。可重试，不会重复发布。';}finally{button.disabled=false;}});
 let positionTimer;
 function remember(){saved.y=Math.round(window.scrollY);persist();}
 window.addEventListener('scroll',()=>{clearTimeout(positionTimer);positionTimer=setTimeout(remember,350);},{passive:true});window.addEventListener('pagehide',remember);
 window.addEventListener('load',()=>{if(location.hash==='#comments')openPanel('comments');else if(location.hash){document.getElementById(decodeURIComponent(location.hash.slice(1)))?.scrollIntoView();}else if(saved.y)window.scrollTo(0,saved.y);});
})();

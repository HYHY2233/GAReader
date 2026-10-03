'use strict';
(() => {
  const NORMALIZATION='nfc-whitespace-v1';
  function logical(element,{breaks=false}={}) {
    let raw=''; const slots=[];
    const walk=document.createTreeWalker(element,NodeFilter.SHOW_TEXT|NodeFilter.SHOW_ELEMENT,{
      acceptNode(n){
        if(n.nodeType===Node.ELEMENT_NODE) {
          if(n.matches('annotation,script,style,button,[data-reader-control]'))return NodeFilter.FILTER_REJECT;
          return breaks&&n.tagName==='BR'?NodeFilter.FILTER_ACCEPT:NodeFilter.FILTER_SKIP;
        }
        return NodeFilter.FILTER_ACCEPT;
      }
    });
    let n;
    while((n=walk.nextNode())) {
      const value=n.nodeType===Node.TEXT_NODE?n.data:'\n';
      if(n.nodeType===Node.TEXT_NODE)for(let i=0;i<value.length;i++)slots.push({start:[n,i],end:[n,i+1]});
      else {const index=[...n.parentNode.childNodes].indexOf(n);slots.push({start:[n.parentNode,index],end:[n.parentNode,index+1]});}
      raw+=value;
    }
    const groups=globalThis.Intl?.Segmenter?[...new Intl.Segmenter(undefined,{granularity:'grapheme'}).segment(raw)]:
      [...raw.matchAll(/\P{M}\p{M}*|\p{M}+/gu)].map(m=>({index:m.index,segment:m[0]}));
    const chars=[],points=[];
    for(const group of groups) {
      const start=group.index,end=start+group.segment.length;
      // A normalized cluster can span text nodes (for example e + combining acute).
      for(let char of group.segment.normalize('NFC')) {
        const point={start:slots[start].start,end:slots[end-1].end};
        if(/\s/u.test(char)) {
          if(!chars.length)continue;
          if(chars.at(-1)===' '){points.at(-1).end=point.end;continue;}
          char=' ';
        }
        chars.push(char);points.push(point);
      }
    }
    if(chars.at(-1)===' '){chars.pop();points.pop();}
    return {raw,text:chars.join(''),chars,points,element};
  }
  function compare(a,b) {
    const first=document.createRange(),second=document.createRange();
    first.setStart(...a);first.collapse(true);second.setStart(...b);second.collapse(true);
    return first.compareBoundaryPoints(Range.START_TO_START,second);
  }
  function offsets(range,map) {
    const start=[range.startContainer,range.startOffset],end=[range.endContainer,range.endOffset];
    let lo=0,hi=map.points.length;
    while(lo<hi){const mid=(lo+hi)>>1;if(compare(map.points[mid].end,start)<=0)lo=mid+1;else hi=mid;}
    const from=lo;lo=0;hi=map.points.length;
    while(lo<hi){const mid=(lo+hi)>>1;if(compare(map.points[mid].start,end)<0)lo=mid+1;else hi=mid;}
    return [from,lo];
  }
  function restore(map,start,end) {
    if(!Number.isInteger(start)||!Number.isInteger(end)||start<0||end>map.points.length||start>=end)return null;
    const range=document.createRange();range.setStart(...map.points[start].start);range.setEnd(...map.points[end-1].end);return range;
  }
  function selected(range,map) {
    const [start,end]=offsets(range,map);
    if(start>=end)return null;
    const part=restore(map,start,end);
    return {start,end,quote:map.chars.slice(start,end).join(''),raw_quote:part.toString(),range:part};
  }
  window.GAReaderText={NORMALIZATION,logical,restore,selected,compare};
})();

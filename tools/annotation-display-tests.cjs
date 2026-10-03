const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const {build}=require('../app/static/annotation-display.js'),checks=[];
const context={view:'both',revision:'r',pdfHash:'hash',units:new Set(['u1','u2']),representations:new Set(['u1::zh','u1::en','u2::zh'])};
const source={revision_id:'r',created_view:'both',source_language:'zh',kind:'text',segments:[{unit_id:'u1',representation_id:'u1::zh'}]};
const exact={source_segment_index:0,unit_id:'u1',representation_id:'u1::zh',language:'zh',precision:'exact',start:0,end:11,quote:'面对可再生能源的间歇性'},block={source_segment_index:0,unit_id:'u1',language:'en',precision:'block'};
function check(name,fn){fn();checks.push({name,status:'PASS'});}
check('Chinese original wins in both projection orders; one display target, no fallback marker',()=>{
 const a=build({id:1,source,projections:[block,exact]},context),b=build({id:1,source,projections:[exact,block]},context);
 assert.deepEqual(a,b);assert.equal(a.length,1);assert.equal(a[0].precision,'exact');assert.equal(a[0].projection.language,'zh');
});
check('Hidden source switches to English fallback while source remains Chinese',()=>{
 const note={id:1,source,projections:[exact,block]},before=JSON.stringify(note),targets=build(note,{...context,view:'en'});
 assert.equal(targets.length,1);assert.equal(targets[0].precision,'block');assert.equal(targets[0].projection.language,'en');assert.equal(JSON.stringify(note),before);
});
check('Partial exact mapping preserves another original segment with only a block',()=>{
 const mixed={id:1,source:{...source,segments:[...source.segments,{unit_id:'u2',representation_id:'u2::zh'}]},projections:[exact,block,{source_segment_index:1,unit_id:'u2',language:'zh',precision:'block'}]};
 const targets=build(mixed,context);assert.deepEqual(targets.map(t=>[t.source_segment_index,t.precision]),[[0,'exact'],[1,'block']]);
});
check('One source segment spanning PDF page fragments keeps both pages deterministically',()=>{
 const note={id:2,source,projections:[{source_segment_index:0,precision:'exact',page_index:1,quads:[[1,2,3,4]]},{source_segment_index:0,precision:'exact',page_index:0,quads:[[1,2,3,4]]}]};
 assert.deepEqual(build(note,{...context,view:'pdf'}).map(t=>t.projection.page_index),[0,1]);
});
check('PDF selection overlapping multiple HTML units keeps unit coverage, one language per unit',()=>{
 const note={id:3,source:{...source,created_view:'pdf',source_language:'en',pdf_sha256:'hash',segments:[{page_index:0}]},projections:[]};
 for(const unit_id of ['u1','u2'])for(const language of ['zh','en'])note.projections.push({source_segment_index:0,unit_id,language,precision:'block'});
 const targets=build(note,context);assert.equal(targets.length,2);assert.ok(targets.every(t=>t.projection.language==='en'));
});
check('Whole objects and stale segments never become an invented exact range',()=>{
 const object=build({id:4,source:{...source,kind:'object'},projections:[{source_segment_index:0,unit_id:'u1',language:'shared',precision:'object'}]},context);
 assert.equal(object[0].precision,'object');
 const stale=build({id:5,source,projections:[{source_segment_index:0,precision:'stale',reason:'changed'}]},context);assert.equal(stale[0].precision,'stale');
});
const out=path.join(__dirname,'../evidence/root-cause-v4');fs.mkdirSync(out,{recursive:true});fs.writeFileSync(path.join(out,'display-plan-tests.json'),JSON.stringify({kind:'pure-function regression; not browser geometry evidence',checks},null,2));console.log(JSON.stringify({checks}));

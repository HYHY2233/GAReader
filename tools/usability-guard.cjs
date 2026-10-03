// Refuse a different (including production) instance before logging in or writing test data.
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
module.exports=async function isolated(page,base,directory){
  assert.ok(['working','restored-verified'].includes(directory),'Unknown isolated fixture');
  const config=JSON.parse(fs.readFileSync(path.join(__dirname,'..','test-runs','usability-v3',directory,'local.json'),'utf8'));
  assert.ok(config.instance_id,'Missing isolated instance identifier');
  const response=await page.request.get(base+'/healthz/');
  assert.ok(response.ok(),'Isolated server is unavailable');
  assert.equal((await response.json()).instance,config.instance_id,'Refuse non-isolated server');
};

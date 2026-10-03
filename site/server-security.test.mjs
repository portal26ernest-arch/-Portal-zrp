import { test } from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, readFile, writeFile, mkdir, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { spawn } from 'node:child_process';
import { request } from 'node:http';

const source = await readFile(new URL('./server.mjs', import.meta.url), 'utf8');
function get(port, target, host = 'localhost', method = 'GET') {
  return new Promise((resolve, reject) => {
    const req = request({ hostname:'127.0.0.1', port, path:target, method, headers:{Host:host} }, res => {
      let body='';res.on('data', data=>body+=data);res.on('end',()=>resolve({status:res.statusCode,body}));
    });
    req.on('error',reject);req.setTimeout(3000,()=>req.destroy(new Error('test timeout')));req.end();
  });
}

test('malformed URL and async errors do not kill isolated site; valid requests still work', async () => {
  const dir=await mkdtemp(path.join(tmpdir(),'portal-site-security-'));
  let child;
  try {
    await mkdir(path.join(dir,'public'));
    await writeFile(path.join(dir,'public','index.html'),'synthetic-static-control');
    const injected=source.replace('async function handleRequest(req, res) {',
      'async function handleRequest(req, res) { if(req.url === "/__fixture_error") throw new Error("fixture-private-error");');
    await writeFile(path.join(dir,'server.mjs'),injected+'\nserver.on("listening",()=>console.log("TEST_PORT="+server.address().port));\n');
    child=spawn(process.execPath,[path.join(dir,'server.mjs')],{env:{PORT:'0',HOST:'127.0.0.1',LANG:'C.UTF-8'},stdio:['ignore','pipe','pipe']});
    const port=await new Promise((resolve,reject)=>{
      let output='';const timer=setTimeout(()=>reject(new Error('isolated listener did not start')),5000);
      child.stdout.on('data',data=>{output+=data;const match=output.match(/TEST_PORT=(\d+)/);if(match){clearTimeout(timer);resolve(Number(match[1]));}});
      child.once('exit',()=>{clearTimeout(timer);reject(new Error('isolated site exited before readiness'));});
    });
    for(const target of ['/%FF','/%E0%A4%A','/%','/%C0%AF']) {
      assert.equal((await get(port,target)).status,400);
      assert.equal((await get(port,'/')).body,'synthetic-static-control');
      assert.equal(child.exitCode,null);
    }
    assert.equal((await get(port,'/','[')).status,400);
    const failure=await get(port,'/__fixture_error');
    assert.equal(failure.status,500);assert.equal(failure.body.includes('fixture-private-error'),false);
    assert.equal((await get(port,'/')).status,200);
    assert.equal((await get(port,'/','localhost','HEAD')).body,'');
    assert.equal((await get(port,'/api/leads')).status,200);
    assert.equal(child.exitCode,null);
  } finally {
    if(child && child.exitCode===null){child.kill();await new Promise(resolve=>child.once('exit',resolve));}
    await rm(dir,{recursive:true,force:true});
  }
});

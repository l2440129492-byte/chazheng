const {test} = require('node:test');
const assert = require('node:assert/strict');
const {mkdtemp, readFile, rm, writeFile} = require('node:fs/promises');
const {tmpdir} = require('node:os');
const path = require('node:path');

test('跨平台服务：页面、配置状态、转发与报告保存', async t => {
  const {createApp, loadConfig} = require('../server.cjs');
  const dir = await mkdtemp(path.join(tmpdir(), 'detective-'));
  t.after(() => rm(dir, {recursive:true, force:true}));
  await writeFile(path.join(dir, '.env'), 'YB_API_KEY="search-secret"\nLLM_API_KEY=model-secret\nLLM_MODEL=test-model\n');
  const config = loadConfig(dir, {});
  assert.equal(config.YB_API_KEY, 'search-secret');
  const requests = [];
  const upstream = require('node:http').createServer(async (req,res) => {
    let body = ''; for await (const chunk of req) body += chunk;
    requests.push({url:req.url, auth:req.headers.authorization, body:JSON.parse(body)});
    res.writeHead(req.url === '/search' ? 429 : 200, {'Content-Type':'application/json'});
    res.end(req.url === '/search' ? '{"Response":{"Error":{"Code":"Limit","Message":"稍后再试"}}}' : '{"choices":[]}');
  });
  await new Promise(r => upstream.listen(0, '127.0.0.1', r));
  t.after(() => new Promise(r => upstream.close(r)));
  const upstreamUrl = `http://127.0.0.1:${upstream.address().port}`;
  const app = createApp({dir, config:{...config, LLM_BASE_URL:upstreamUrl}, searchUrl:upstreamUrl+'/search'});
  await writeFile(path.join(dir, 'index.html'), '<h1>考据侦探</h1>');
  await new Promise(r => app.listen(0, '127.0.0.1', r));
  t.after(() => new Promise(r => app.close(r)));
  const base = `http://127.0.0.1:${app.address().port}`;
  const post = (url, body) => fetch(base+url, {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(body)});
  assert.match(await (await fetch(base)).text(), /考据侦探/);
  await writeFile(path.join(dir, 'catalog.js'), 'window.WORK_CATALOG = {};');
  const catalog = await fetch(base+'/catalog.js');
  assert.equal(catalog.status, 200);
  assert.match(catalog.headers.get('content-type'), /javascript/);
  assert.match(await catalog.text(), /WORK_CATALOG/);
  const status = await (await fetch(base+'/api/status')).json();
  assert.equal(status.key, true); assert.equal(status.llm, true);
  assert.ok(!JSON.stringify(status).includes('secret'));
  assert.equal((await fetch(base+'/.env')).status, 404);
  const search = await post('/api/search', {Query:'孔子', Mode:0, Cnt:5, injected:'x'});
  assert.equal(search.status, 429);
  assert.equal((await search.json()).Response.Error.Code, 'Limit');
  assert.deepEqual(requests[0].body, {Query:'孔子', Mode:0, Cnt:5});
  assert.equal(requests[0].auth, 'Bearer search-secret');
  await post('/api/llm', {messages:[{role:'user',content:'查证'}],json:true,max_tokens:300,model:'untrusted'});
  assert.equal(requests[1].url, '/chat/completions');
  assert.equal(requests[1].body.model, 'test-model');
  assert.deepEqual(requests[1].body.response_format, {type:'json_object'});
  const saved = await (await post('/api/save', {name:'../../孔子',markdown:'原文',json:'{}',html:'<p>报告</p>'})).json();
  assert.equal(saved.ok, true);
  assert.equal(await readFile(path.join(dir,saved.file),'utf8'), '原文');
  assert.equal(await readFile(path.join(dir,saved.file.replace(/\.md$/,'.html')),'utf8'), '<p>报告</p>');
  assert.equal((await (await fetch(base+'/api/status')).json()).calls, 1);
  assert.equal((await fetch(base+'/api/save', {method:'POST',body:'{'})).status, 400);
});

test('未配置密钥仍可启动，但真实查询明确报错', async t => {
  const {createApp} = require('../server.cjs');
  const app = createApp({config:{}});
  await new Promise(r => app.listen(0,'127.0.0.1',r));
  t.after(() => new Promise(r => app.close(r)));
  const base = `http://127.0.0.1:${app.address().port}`;
  const status = await (await fetch(base+'/api/status')).json();
  assert.equal(status.key,false); assert.equal(status.llm,false);
  for (const endpoint of ['search','llm']) {
    const res = await fetch(base+'/api/'+endpoint,{method:'POST',body:'{}'});
    assert.equal(res.status,400); assert.match((await res.json()).error,/API_KEY/);
  }
});

test('连接失败能区分元宝和模型，不泄露密钥', async t => {
  const http = require('node:http');
  const portProbe = http.createServer();
  await new Promise(r => portProbe.listen(0,'127.0.0.1',r));
  const unavailable = `http://127.0.0.1:${portProbe.address().port}`;
  await new Promise(r => portProbe.close(r));
  const {createApp} = require('../server.cjs');
  const app=createApp({config:{YB_API_KEY:'private-search',LLM_API_KEY:'private-model',LLM_BASE_URL:unavailable},searchUrl:unavailable});
  await new Promise(r=>app.listen(0,'127.0.0.1',r));
  t.after(()=>new Promise(r=>app.close(r)));
  for (const [endpoint,body,label] of [['search',{Query:'测试'},'元宝搜索'],['llm',{messages:[],stage:'拆解'},'大模型']]) {
    const res=await fetch(`http://127.0.0.1:${app.address().port}/api/${endpoint}`,{method:'POST',body:JSON.stringify(body)});
    assert.equal(res.status,502);
    const data=await res.json();
    assert.match(data.error,new RegExp(label));
    assert.equal(data.code,'ECONNREFUSED');
    assert.ok(!JSON.stringify(data).includes('private-'));
  }
});

test('上游首次重置连接时仅重试一次并恢复', async t => {
  let attempts=0;
  const upstream=require('node:http').createServer((req,res)=>{
    attempts++;
    if(attempts===1){req.socket.destroy();return;}
    res.writeHead(200,{'Content-Type':'application/json'});res.end('{"choices":[]}');
  });
  await new Promise(r=>upstream.listen(0,'127.0.0.1',r));
  t.after(()=>new Promise(r=>upstream.close(r)));
  const {createApp}=require('../server.cjs');
  const app=createApp({config:{LLM_API_KEY:'test',LLM_BASE_URL:`http://127.0.0.1:${upstream.address().port}`}});
  await new Promise(r=>app.listen(0,'127.0.0.1',r));
  t.after(()=>new Promise(r=>app.close(r)));
  const res=await fetch(`http://127.0.0.1:${app.address().port}/api/llm`,{method:'POST',body:JSON.stringify({messages:[]})});
  assert.equal(res.status,200);assert.equal(attempts,2);
});

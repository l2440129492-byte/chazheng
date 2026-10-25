// Mac / Linux / Windows 本地服务，Node.js 18+，无需安装依赖。
const http = require('node:http');
const fs = require('node:fs');
const path = require('node:path');
const {randomUUID} = require('node:crypto');

function loadConfig(dir = __dirname, env = process.env) {
  const config = {LLM_BASE_URL:'https://api.deepseek.com', LLM_MODEL:'deepseek-chat'};
  const envPath = path.join(dir, '.env');
  if (fs.existsSync(envPath)) {
    for (const line of fs.readFileSync(envPath,'utf8').split(/\r?\n/)) {
      const match = line.match(/^\s*(YB_API_KEY|LLM_API_KEY|LLM_BASE_URL|LLM_MODEL)\s*=\s*(.*?)\s*$/);
      if (match) config[match[1]] = match[2].replace(/^(["'])(.*)\1$/, '$2');
    }
  }
  for (const key of ['YB_API_KEY','LLM_API_KEY','LLM_BASE_URL','LLM_MODEL']) {
    if (env[key]) config[key] = env[key];
  }
  return config;
}

function createApp({dir = __dirname, config = loadConfig(dir), searchUrl = 'https://api.wsa.cloud.tencent.com/SearchPro'} = {}) {
  let calls = 0;
  return http.createServer(async (req,res) => {
    const send = (status, body, type = 'application/json; charset=utf-8') => {
      res.writeHead(status, {'Content-Type':type, 'Cache-Control':'no-store'});
      res.end(typeof body === 'string' ? body : JSON.stringify(body));
    };
    try {
      const route = new URL(req.url,'http://localhost').pathname;
      if (req.method === 'GET' && ['/', '/index.html'].includes(route)) {
        return send(200, await fs.promises.readFile(path.join(dir,'index.html'),'utf8'),'text/html; charset=utf-8');
      }
      if (req.method === 'GET' && route === '/catalog.js') {
        return send(200, await fs.promises.readFile(path.join(dir,'catalog.js'),'utf8'),'text/javascript; charset=utf-8');
      }
      if (req.method === 'GET' && route === '/api/status') {
        return send(200, {key:!!config.YB_API_KEY, llm:!!config.LLM_API_KEY, model:config.LLM_MODEL || 'deepseek-chat', calls, server:'node'});
      }
      if (req.method !== 'POST' || !['/api/search','/api/llm','/api/save'].includes(route)) return send(404,{error:'not found'});
      // 仅接受本地页面的请求；不向网页提供密钥或任意文件。
      if (req.headers.origin && req.headers.origin !== `http://${req.headers.host}`) return send(403,{error:'不接受其他网站的请求'});
      let raw = '';
      for await (const chunk of req) {
        raw += chunk;
        if (Buffer.byteLength(raw) > 10 * 1024 * 1024) return send(413,{error:'请求内容过大'});
      }
      let input;
      try { input = JSON.parse(raw); } catch { return send(400,{error:'请求必须是有效 JSON'}); }
      if (!input || typeof input !== 'object' || Array.isArray(input)) return send(400,{error:'请求必须是 JSON 对象'});
      if (route === '/api/save') {
        const name = String(input.name || '报告').replace(/[\\/:*?"<>|\s.]+/g,'_').slice(0,40);
        const stamp = new Date().toISOString().replace(/[:.]/g,'-');
        const stem = `${stamp}_${name}_${randomUUID().slice(0,8)}`;
        const reports = path.join(dir,'reports');
        await fs.promises.mkdir(reports,{recursive:true});
        for (const [ext, value] of [['md',input.markdown],['json',input.json],['html',input.html]]) {
          if (ext === 'html' && !value) continue;
          await fs.promises.writeFile(path.join(reports,`${stem}.${ext}`),String(value ?? ''),'utf8');
        }
        return send(200,{ok:true,file:`reports/${stem}.md`});
      }
      const isSearch = route === '/api/search';
      const key = isSearch ? config.YB_API_KEY : config.LLM_API_KEY;
      if (!key) return send(400,{error:`没有配置 ${isSearch ? 'YB_API_KEY' : 'LLM_API_KEY'}，请填写 web/.env 后重启服务`});
      let body;
      if (isSearch) {
        if (typeof input.Query !== 'string' || !input.Query.trim()) return send(400,{error:'请输入搜索词'});
        body = {Query:input.Query};
        for (const key of ['Mode','Cnt','Site','Freshness']) if (input[key] != null) body[key] = input[key];
        calls++;
      } else {
        if (!Array.isArray(input.messages)) return send(400,{error:'messages 必须是数组'});
        body = {model:config.LLM_MODEL || 'deepseek-chat',temperature:0,messages:input.messages};
        if (input.max_tokens) body.max_tokens = input.max_tokens;
        if (input.json) body.response_format = {type:'json_object'};
      }
      const url = isSearch ? searchUrl : `${(config.LLM_BASE_URL || 'https://api.deepseek.com').replace(/\/$/,'')}/chat/completions`;
      const service = isSearch ? '元宝搜索' : `大模型（${config.LLM_MODEL || 'deepseek-chat'}）`;
      const stage = isSearch ? '搜索' : String(input.stage || '调用').slice(0,30);
      // 仅在未收到 HTTP 响应时重试一次短暂网络故障；读响应失败不重试。
      const retryable = new Set(['UND_ERR_CONNECT_TIMEOUT','EAI_AGAIN','ECONNREFUSED','ECONNRESET','UND_ERR_SOCKET']);
      const signal = AbortSignal.timeout(isSearch ? 30000 : 120000);
      let upstream;
      for (let attempt = 0; attempt < 2; attempt++) {
        try {
          upstream = await fetch(url,{method:'POST',headers:{'Content-Type':'application/json',Authorization:`Bearer ${key}`},body:JSON.stringify(body),signal});
          break;
        } catch (error) {
          const code = error.cause?.code || error.code || error.name;
          if (!attempt && retryable.has(code) && !signal.aborted) continue;
          const timeout = signal.aborted || error.name === 'TimeoutError' || code === 'UND_ERR_CONNECT_TIMEOUT';
          console.error(`[${isSearch ? 'search' : 'llm'}] ${stage}: ${code}`);
          return send(502,{error:`${service}在“${stage}”阶段${timeout ? '连接或响应超时，请稍后重试' : '连接失败，请检查该服务的网络或地址'}（${code}）`,service:isSearch ? 'yuanbao' : 'llm',stage,code});
        }
      }
      try {
        return send(upstream.status,await upstream.text());
      } catch (error) {
        const code = error.cause?.code || error.name;
        return send(502,{error:`${service}在“${stage}”阶段响应中断或超时，请重试（${code}）`,service:isSearch ? 'yuanbao' : 'llm',stage,code});
      }
    } catch {
      return send(500,{error:'本地服务处理失败，请检查文件权限或重启服务'});
    }
  });
}

if (require.main === module) {
  const config = loadConfig();
  const app = createApp({config});
  let port = Number(process.env.PORT || 8765);
  const firstPort = port;
  app.on('error', error => {
    if (error.code === 'EADDRINUSE' && !process.env.PORT && port < firstPort + 10) {
      port++;
      app.listen(port, '127.0.0.1');
      return;
    }
    console.error(error.code === 'EADDRINUSE' ? `端口 ${port} 已被占用，请关闭旧服务或换一个 PORT。` : `启动失败：${error.message}`);
    process.exitCode = 1;
  });
  app.on('listening', () => {
    console.log(`元宝考据侦探已启动：http://127.0.0.1:${app.address().port}`);
    console.log(config.YB_API_KEY ? '元宝搜索：已配置' : '元宝搜索：未配置，请填写 web/.env 中的 YB_API_KEY 后重启');
    console.log(config.LLM_API_KEY ? `模型判断：${config.LLM_MODEL}` : '模型判断：未配置 LLM_API_KEY，使用规则模式');
    console.log('按 Control+C 停止服务。');
    if (process.argv.includes('--open') && process.platform === 'darwin') {
      require('node:child_process').spawn('open', [`http://127.0.0.1:${app.address().port}`], {stdio:'ignore'}).on('error', () => {});
    }
  });
  app.listen(port,'127.0.0.1');
}
module.exports = {createApp,loadConfig};

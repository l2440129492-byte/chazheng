// Cloudflare Pages 单文件 Worker：接管全部路由。
// 静态资源经 env.ASSETS 分发；/api/* 在此代理，密钥来自 Pages 环境变量，不进仓库、不进浏览器。
const JSON_HEADERS = { 'Content-Type': 'application/json; charset=utf-8' };

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (url.pathname.startsWith('/api/')) return handleApi(request, env, url);
    return env.ASSETS.fetch(request);
  },
};

async function handleApi(request, env, url) {
  if (request.method === 'GET' && url.pathname === '/api/status') {
    return Response.json({
      key: !!env.YB_API_KEY,
      llm: !!env.LLM_API_KEY,
      model: env.LLM_MODEL || 'deepseek-flash',
      calls: 0,
      server: 'cloudflare',
    });
  }
  if (request.method !== 'POST') return Response.json({ error: 'not found' }, { status: 404, headers: JSON_HEADERS });

  let input;
  try { input = await request.json(); } catch {
    return Response.json({ error: '请求必须是有效 JSON' }, { status: 400, headers: JSON_HEADERS });
  }
  if (!input || typeof input !== 'object' || Array.isArray(input)) {
    return Response.json({ error: '请求必须是 JSON 对象' }, { status: 400, headers: JSON_HEADERS });
  }

  const isSearch = url.pathname === '/api/search';
  if (!isSearch && url.pathname !== '/api/llm') {
    return Response.json({ error: 'not found' }, { status: 404, headers: JSON_HEADERS });
  }

  const key = isSearch ? env.YB_API_KEY : env.LLM_API_KEY;
  if (!key) {
    return Response.json({ error: `没有配置 ${isSearch ? 'YB_API_KEY' : 'LLM_API_KEY'}（Cloudflare Pages 环境变量）` }, { status: 400, headers: JSON_HEADERS });
  }

  let body, target;
  if (isSearch) {
    if (typeof input.Query !== 'string' || !input.Query.trim()) {
      return Response.json({ error: '请输入搜索词' }, { status: 400, headers: JSON_HEADERS });
    }
    body = { Query: input.Query };
    for (const k of ['Mode', 'Cnt', 'Site', 'Freshness']) if (input[k] != null) body[k] = input[k];
    target = 'https://api.wsa.cloud.tencent.com/SearchPro';
  } else {
    if (!Array.isArray(input.messages)) {
      return Response.json({ error: 'messages 必须是数组' }, { status: 400, headers: JSON_HEADERS });
    }
    body = { model: env.LLM_MODEL || 'deepseek-flash', temperature: 0, messages: input.messages };
    if (input.max_tokens) body.max_tokens = input.max_tokens;
    if (input.json) body.response_format = { type: 'json_object' };
    target = `${(env.LLM_BASE_URL || 'https://api.deepseek.com').replace(/\/$/, '')}/chat/completions`;
  }

  const stage = String(input.stage || '调用').slice(0, 30);
  const service = isSearch ? '元宝搜索' : `大模型（${env.LLM_MODEL || 'deepseek-flash'}）`;
  try {
    const upstream = await fetch(target, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${key}` },
      body: JSON.stringify(body),
    });
    return new Response(upstream.body, { status: upstream.status, headers: JSON_HEADERS });
  } catch (error) {
    return Response.json(
      { error: `${service}在「${stage}」阶段连接失败，请重试（${error.message}）`, service: isSearch ? 'yuanbao' : 'llm', stage },
      { status: 502, headers: JSON_HEADERS },
    );
  }
}

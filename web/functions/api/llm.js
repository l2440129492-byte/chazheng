// Cloudflare Pages Function：转发 OpenAI 兼容大模型接口，密钥保存在 Pages 环境变量。
export async function onRequestPost({ request, env }) {
  if (!env.LLM_API_KEY) {
    return Response.json({ error: '没有配置 LLM_API_KEY，请在 Cloudflare Pages 设置里添加环境变量' }, { status: 400 });
  }
  let input;
  try { input = await request.json(); } catch {
    return Response.json({ error: '请求必须是有效 JSON' }, { status: 400 });
  }
  if (!Array.isArray(input.messages)) {
    return Response.json({ error: 'messages 必须是数组' }, { status: 400 });
  }
  const body = { model: env.LLM_MODEL || 'deepseek-flash', temperature: 0, messages: input.messages };
  if (input.max_tokens) body.max_tokens = input.max_tokens;
  if (input.json) body.response_format = { type: 'json_object' };
  const url = `${(env.LLM_BASE_URL || 'https://api.deepseek.com').replace(/\/$/, '')}/chat/completions`;
  try {
    const upstream = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${env.LLM_API_KEY}` },
      body: JSON.stringify(body),
    });
    return new Response(upstream.body, { status: upstream.status, headers: { 'Content-Type': 'application/json; charset=utf-8' } });
  } catch (error) {
    return Response.json({ error: `大模型转发失败（${error.message}）` }, { status: 502 });
  }
}

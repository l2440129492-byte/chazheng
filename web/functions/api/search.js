// Cloudflare Pages Function：转发元宝搜索，密钥保存在 Pages 环境变量。
const SEARCH_URL = 'https://api.wsa.cloud.tencent.com/SearchPro';

export async function onRequestPost({ request, env }) {
  if (!env.YB_API_KEY) {
    return Response.json({ error: '没有配置 YB_API_KEY，请在 Cloudflare Pages 设置里添加环境变量' }, { status: 400 });
  }
  let input;
  try { input = await request.json(); } catch {
    return Response.json({ error: '请求必须是有效 JSON' }, { status: 400 });
  }
  const body = { Query: input.Query };
  for (const key of ['Mode', 'Cnt', 'Site', 'Freshness']) if (input[key] != null) body[key] = input[key];
  try {
    const upstream = await fetch(SEARCH_URL, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${env.YB_API_KEY}` },
      body: JSON.stringify(body),
    });
    return new Response(upstream.body, { status: upstream.status, headers: { 'Content-Type': 'application/json; charset=utf-8' } });
  } catch (error) {
    return Response.json({ error: `元宝搜索转发失败（${error.message}）` }, { status: 502 });
  }
}

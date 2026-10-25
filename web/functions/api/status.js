// Cloudflare Pages Function：状态接口。密钥配置在 Pages 环境变量（YB_API_KEY / LLM_API_KEY），不进仓库。
export async function onRequestGet({ env }) {
  return Response.json({
    key: !!env.YB_API_KEY,
    llm: !!env.LLM_API_KEY,
    model: env.LLM_MODEL || 'deepseek-flash',
    calls: 0,
    server: 'cloudflare',
  });
}

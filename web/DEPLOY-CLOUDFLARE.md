# 部署到 Cloudflare Pages（免费额度即可）

网页版托管在 Cloudflare Pages：静态页面由 Pages 分发，`/api/search`、`/api/llm`、`/api/status` 由 `web/_worker.js`（单文件 Worker，高级模式）代理，密钥放在 Pages 环境变量，不进仓库、不进浏览器。Pages 没有本地文件系统，保存报告会自动回退为浏览器下载（.html / .md / .json）。

当前线上地址：https://chazheng-detective.pages.dev

## 一次性部署（已按此完成过）

```bash
# 构建：无需构建，静态文件即 web/ 目录（不要把 web/.env 传上去）
rm -rf /tmp/cf-dist && mkdir /tmp/cf-dist
cp web/index.html web/catalog.js web/_worker.js /tmp/cf-dist/

# 部署（需先 wrangler login 或导出 CLOUDFLARE_API_TOKEN）
npx -y wrangler@latest pages deploy /tmp/cf-dist --project-name chazheng-detective --branch main --commit-dirty=true

# 密钥（从 web/.env 读入，不在终端回显）
for kv in YB_API_KEY LLM_API_KEY LLM_BASE_URL LLM_MODEL; do
  v=$(sed -n "s/^${kv}=//p" web/.env | head -1 | tr -d '"')
  [ -n "$v" ] && printf '%s' "$v" | npx -y wrangler@latest pages secret put "$kv" --project-name chazheng-detective
done

# secret 修改后需重新部署一次才生效，然后验证
curl -s https://chazheng-detective.pages.dev/api/status   # 期望 {"key":true,"llm":true,...}
```

## 注意

- 元宝搜索接口的 `Cnt` 只接受 10 的倍数（10/20…），前端已按此传参；手工调试别用 Cnt=3/5。
- 不要把密钥写进 `wrangler.toml` 或提交仓库，只使用 Pages secrets。
- 本机 wrangler OAuth 过期时，可按 `tianyuan-site/deploy-pages.sh` 的方式用 refresh_token 续期（配置位于 `~/Library/Preferences/.wrangler/config/default.toml`）。
- 国内访问 pages.dev 可能不稳定；比赛现场演示建议同时备好本地 `node web/server.cjs`。

## 资源需求

- 本地 Node 服务：Node 18+，零依赖，单进程常驻内存约 50–80MB，1 核 512MB 的最低配 VPS 即可。
- Cloudflare Pages 免费档：Functions 每天十万次请求免费；单次查证约 5–15 次搜索 + 3–8 次模型调用，演示绰绰有余。主要成本在元宝搜索与模型自身的调用额度。

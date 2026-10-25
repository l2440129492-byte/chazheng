# 部署到 Cloudflare Pages（免费额度即可）

网页版可以托管在 Cloudflare Pages：静态页面直接由 Pages 分发，`/api/search`、`/api/llm`、`/api/status` 由同目录 `functions/api/` 下的 Pages Functions 代理，密钥放在 Pages 环境变量里，不会进入仓库或浏览器。Pages 没有本地文件系统，保存报告会自动改为浏览器直接下载（.html / .md / .json）。

## 步骤

1. 安装并登录 Wrangler（一次性）：

   ```bash
   npm install -g wrangler
   wrangler login
   ```

2. 部署（在仓库根目录运行；项目名决定演示地址，封面使用 `chazheng-detective.pages.dev`）：

   ```bash
   wrangler pages deploy web --project-name chazheng-detective
   ```

3. 在 Cloudflare 控制台 → Workers & Pages → chazheng-detective → Settings → Environment variables 添加（Production 与 Preview 都加）：

   | 变量 | 值 |
   |---|---|
   | `YB_API_KEY` | 元宝搜索服务 API Key |
   | `LLM_API_KEY` | DeepSeek 等 OpenAI 兼容模型 Key |
   | `LLM_BASE_URL` | 可选，默认 `https://api.deepseek.com` |
   | `LLM_MODEL` | 可选，默认 `deepseek-flash` |

4. 重新部署一次让环境变量生效，打开 `https://chazheng-detective.pages.dev` 验证左下角状态显示「侦探模式」。

## 资源需求

- 本地 Node 服务：Node 18+，单进程常驻内存约 50–80MB，CPU 可忽略，任意最低配 VPS（1 核 512MB）甚至免费容器都够。
- Cloudflare Pages 免费档：静态请求不限量级远超需求，Functions 每天十万次请求免费；单次查证约消耗 5–15 次搜索 + 3–8 次模型调用，足够演示使用。主要成本在元宝搜索与模型自身的调用额度。

## 注意

- 不要把密钥写进 `wrangler.toml` 提交到仓库，只使用控制台环境变量或 `wrangler pages secret put`。
- 国内访问 pages.dev 可能不稳定，如需稳定演示可绑定自定义域名，或继续用本地 `node web/server.cjs`。

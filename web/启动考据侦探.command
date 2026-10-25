#!/bin/zsh
cd "${0:A:h}"
export PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:$PATH"
if ! command -v node >/dev/null 2>&1; then
  echo '请先安装 Node.js 18 或更新版本：https://nodejs.org/'
  read '?按回车退出'
  exit 1
fi
if [[ ! -f .env ]]; then
  cp .env.example .env
  echo '已创建 web/.env，请填写元宝搜索和模型密钥后重启；现在可以先浏览页面。'
fi
node server.cjs --open
read '?服务已停止，按回车关闭窗口'

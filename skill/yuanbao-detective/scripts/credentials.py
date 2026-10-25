"""本地一次性密钥输入页。只用标准库，不输出密钥，不写项目目录。"""
import argparse
import getpass
import json
import os
import re
from pathlib import Path
import secrets
import stat
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import webbrowser


def credential_path():
    return Path.home() / '.config' / 'yuanbao-detective' / 'credentials.json'


def read_key(dest=None):
    dest = Path(dest) if dest is not None else credential_path()
    if not dest.exists():
        return None
    if dest.is_symlink():
        raise ValueError('密钥文件不能是符号链接')
    if os.name == 'posix' and stat.S_IMODE(dest.stat().st_mode) & 0o077:
        raise ValueError('密钥文件权限过宽，请先将权限设为 600')
    key = json.loads(dest.read_text(encoding='utf-8')).get('YB_API_KEY')
    return key if isinstance(key, str) and key.strip() else None


def resolve_key():
    key = os.environ.get('TENCENTCLOUD_WSA_APIKEY') or os.environ.get('YB_API_KEY')
    if key:
        return key, 'environment'
    key = read_key()
    if key:
        return key, 'local_store'
    legacy = Path.cwd() / '.env'
    if legacy.is_file():
        with legacy.open(encoding='utf-8-sig') as stream:
            for line in stream:
                match = re.match(r"\s*(?:YB_API_KEY|TENCENTCLOUD_WSA_APIKEY)\s*=\s*(.+)", line)
                if match:
                    key = match[1].strip().strip("\"'")
                    if key:
                        return key, 'legacy_env'
    return None, 'none'


def save_key(key, dest=None):
    if not isinstance(key, str) or not key.strip() or len(key) > 4096 or any(c.isspace() for c in key):
        raise ValueError('请输入有效密钥，不要包含空格或换行')
    if os.name != 'posix':
        raise ValueError('当前系统暂不支持受限文件保存，请使用已连接的元宝 MCP 或平台密钥管理')
    dest = Path(dest) if dest is not None else credential_path()
    dest.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
    if dest.parent.is_symlink() or dest.is_symlink():
        raise ValueError('密钥存储位置不能是符号链接')
    os.chmod(dest.parent, 0o700)
    fd, temp = tempfile.mkstemp(prefix='.credential-', dir=dest.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            json.dump({'YB_API_KEY':key}, stream)
        os.replace(temp, dest)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def delete_key(dest=None):
    dest = Path(dest) if dest is not None else credential_path()
    dest.unlink(missing_ok=True)


PAGE = '''<!doctype html><html lang="zh-CN"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>元宝考据侦探 · 首次配置</title>
<style>body{font:17px/1.7 system-ui;background:#f6f7fb;color:#192434;max-width:560px;margin:9vh auto;padding:24px}main{background:white;border-radius:20px;padding:32px;box-shadow:0 8px 40px #18243712}input[type=password]{box-sizing:border-box;width:100%;padding:14px;font:inherit;border:1px solid #aab5c5;border-radius:8px}button{margin-top:20px;padding:12px 24px;background:#2159cb;color:white;border:0;border-radius:8px;font:inherit}small{display:block;color:#526174;margin:16px 0}#status{white-space:pre-line}</style>
<main><h1>连接元宝搜索</h1><p>只需配置搜索密钥。拆解问题和判断证据由你正在使用的 AI 完成，无需另配大模型密钥。</p>
<form id="setup"><label for="key">元宝搜索服务 API Key</label><input type="password" id="key" autocomplete="off" required maxlength="4096" autofocus>
<small>密钥经本机连接交给本地程序，不发送给聊天模型。以后搜索时只发送给腾讯元宝接口。请勿将密钥粘贴到聊天里。</small>
<label><input type="checkbox" id="remember" required> 同意保存在当前用户目录，下次自动使用。</label>
<small>这是本地明文文件，并非系统加密钥匙串。Mac/Linux 限制为仅当前用户可读写（600）；同一用户下的程序仍可读取。可随时运行 credentials.py forget 删除。<span id="remaining" role="timer"></span></small>
<button id="submit">保存并返回 AI 对话</button></form><p role="status" id="status"></p></main>
<script>
const token = location.pathname.slice(1);
const expiresAt = __EXPIRES_AT__;
function updateRemaining(){
 const seconds=Math.max(0,Math.ceil((expiresAt-Date.now())/1000));
 document.querySelector('#remaining').textContent=seconds ? `本页还可填写 ${Math.floor(seconds/60)} 分 ${seconds%60} 秒。` : '输入页已过期，请回到 AI 对话重新打开。';
 if(!seconds && !document.querySelector('#setup').hidden){document.querySelector('#submit').disabled=true;document.querySelector('#status').textContent='输入页已过期，尚未保存。请回到 AI 对话说“重新打开密钥输入页”。';}
}
updateRemaining();setInterval(updateRemaining,1000);
document.querySelector('#setup').onsubmit = async e => {
 e.preventDefault(); const button=document.querySelector('#submit');button.disabled=true;
 try {const r=await fetch('/save',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({token,key:document.querySelector('#key').value,remember:document.querySelector('#remember').checked})});
 const d=await r.json();if(!r.ok)throw Error(d.error);document.querySelector('#key').value='';document.querySelector('#setup').hidden=true;document.querySelector('#status').textContent='已保存。本地输入服务即将关闭，请回到 AI 对话继续查证。';}
 catch(e){document.querySelector('#status').textContent=e instanceof TypeError ? '连接本地输入服务失败，尚未确认保存。服务可能已关闭或输入页已过期。请回到 AI 对话说“重新打开密钥输入页”，不要继续在旧页重试。' : e.message;button.disabled=Date.now()>=expiresAt;}
};
</script></html>'''


def make_server(dest=None, timeout=1800):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass  # 不记录一次性地址、请求或密钥。

        def reply(self, code, body, html=False):
            raw = (body if html else json.dumps(body, ensure_ascii=False)).encode('utf-8')
            self.send_response(code)
            self.send_header('Content-Type', 'text/html; charset=utf-8' if html else 'application/json; charset=utf-8')
            self.send_header('Cache-Control', 'no-store')
            self.send_header('Referrer-Policy', 'no-referrer')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Content-Security-Policy', "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; connect-src 'self'; form-action 'self'; frame-ancestors 'none'; base-uri 'none'")
            self.send_header('Content-Length', str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def valid_host(self):
            return self.headers.get('Host') == '127.0.0.1:%s' % self.server.server_port

        def do_GET(self):
            if not self.valid_host() or self.path != '/' + self.server.token or self.server.saved.is_set():
                return self.reply(404, {'error':'输入页已失效或地址不正确'})
            self.reply(200, PAGE.replace('__EXPIRES_AT__', str(int(self.server.expires_at * 1000))), html=True)

        def do_POST(self):
            self.connection.settimeout(10)
            origin = 'http://127.0.0.1:%s' % self.server.server_port
            if not self.valid_host() or self.headers.get('Origin') != origin:
                return self.reply(403, {'error':'请使用本次打开的本地输入页'})
            if self.path != '/save':
                return self.reply(404, {'error':'not found'})
            try:
                size = int(self.headers.get('Content-Length', '0'))
                if not 0 < size <= 8192:
                    return self.reply(413, {'error':'输入内容过大或为空'})
                data = json.loads(self.rfile.read(size))
                if not isinstance(data, dict) or not secrets.compare_digest(str(data.get('token','')), self.server.token):
                    return self.reply(403, {'error':'本次输入凭证不正确'})
                with self.server.save_lock:
                    if self.server.saved.is_set():
                        return self.reply(409, {'error':'已经保存，请关闭此页'})
                    if data.get('remember') is not True:
                        return self.reply(400, {'error':'请确认同意本地保存后继续'})
                    save_key(data.get('key'), dest)
                    self.server.saved.set()
                self.reply(200, {'ok':True})
            except (ValueError, TypeError):
                self.reply(400, {'error':'输入无效或文件权限不正确，请检查密钥和本地存储位置'})
            except OSError:
                self.reply(500, {'error':'保存失败，请检查本地文件权限'})

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    server.token = secrets.token_urlsafe(32)
    server.expires_at = time.time() + timeout
    server.saved = threading.Event()
    server.save_lock = threading.Lock()
    return server


def setup(timeout=1800, open_browser=True):
    server = make_server(timeout=timeout)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = 'http://127.0.0.1:%s/%s' % (server.server_port, server.token)
    print('请在本机浏览器输入元宝搜索密钥，不要发到聊天中。有效期 30 分钟。\n' + url, flush=True)
    if open_browser:
        try:
            webbrowser.open(url)
        except webbrowser.Error:
            pass
    try:
        if not server.saved.wait(timeout):
            print('输入已超时，未保存新密钥。可重新运行 credentials.py setup。')
            return 1
        print('密钥已保存，可继续查证。')
        return 0
    finally:
        server.shutdown(); server.server_close(); thread.join()


def auth_main(argv=None):
    parser = argparse.ArgumentParser(description='元宝搜索密钥配置（不会输出密钥）')
    parser.add_argument('action', choices=['status','setup','forget','terminal'])
    parser.add_argument('--no-browser', action='store_true', help='只显示输入页地址，不自动打开浏览器')
    args = parser.parse_args(argv)
    if args.action == 'setup':
        return setup(open_browser=not args.no_browser)
    if args.action == 'forget':
        delete_key(); print('已删除本地保存的密钥；环境变量、旧 .env 或 MCP 配置需在原处删除。'); return 0
    if args.action == 'terminal':
        if not sys.stdin.isatty():
            print('请由用户在自己的交互式终端运行；不要通过聊天、管道或命令参数传入密钥。')
            return 2
        key = getpass.getpass('元宝搜索 API Key（不回显）: ').strip()
        if input('同意保存为当前用户目录的受限明文文件？输入 yes: ').strip() != 'yes':
            print('已取消。'); return 1
        save_key(key); print('密钥已保存。'); return 0
    _, source = resolve_key()
    print(json.dumps({'configured':source != 'none','source':source}, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    try:
        sys.exit(auth_main())
    except (OSError, ValueError):
        sys.exit('密钥配置失败，请检查存储权限；不会输出密钥。')

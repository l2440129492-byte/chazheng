# 原作考据侦探 · 本地服务（PowerShell 版，无需安装任何东西）
# 只做两件事：把搜索请求转发给元宝搜索（密钥留在本机），以及把查证报告保存到 reports 文件夹
$ErrorActionPreference = "Stop"
try { [Console]::OutputEncoding = [Text.Encoding]::UTF8 } catch {}
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
$dir = Split-Path -Parent $MyInvocation.MyCommand.Path
$port = 8765

$key = ""
$llmKey = ""; $llmBase = "https://api.deepseek.com"; $llmModel = "deepseek-chat"
$envPath = Join-Path $dir ".env"
if (Test-Path $envPath) {
  foreach ($line in [IO.File]::ReadAllLines($envPath, [Text.Encoding]::UTF8)) {
    if ($line -match "^\s*YB_API_KEY\s*=\s*(.+)$") { $key = $Matches[1].Trim() }
    if ($line -match "^\s*LLM_API_KEY\s*=\s*(.+)$") { $llmKey = $Matches[1].Trim() }
    if ($line -match "^\s*LLM_BASE_URL\s*=\s*(.+)$") { $llmBase = $Matches[1].Trim().TrimEnd("/") }
    if ($line -match "^\s*LLM_MODEL\s*=\s*(.+)$") { $llmModel = $Matches[1].Trim() }
  }
}
if (-not $key) { Write-Host "没找到 YB_API_KEY，请检查 .env 文件"; Read-Host "按回车退出"; exit 1 }
$reports = Join-Path $dir "reports"
New-Item -ItemType Directory -Force -Path $reports | Out-Null
$script:calls = 0

function Invoke-YB([string]$json) {
  $req = [Net.HttpWebRequest]::Create("https://api.wsa.cloud.tencent.com/SearchPro")
  $req.Method = "POST"
  $req.ContentType = "application/json; charset=UTF-8"
  $req.Headers.Add("Authorization", "Bearer $key")
  $req.Timeout = 30000
  $b = [Text.Encoding]::UTF8.GetBytes($json)
  $req.ContentLength = $b.Length
  $s = $req.GetRequestStream(); $s.Write($b, 0, $b.Length); $s.Close()
  try { $resp = $req.GetResponse() }
  catch [Net.WebException] { $resp = $_.Exception.Response; if (-not $resp) { throw } }
  $sr = New-Object IO.StreamReader($resp.GetResponseStream(), [Text.Encoding]::UTF8)
  $t = $sr.ReadToEnd(); $sr.Close(); $resp.Close()
  $script:calls++
  return $t
}

function Invoke-LLM([string]$json) {
  $req = [Net.HttpWebRequest]::Create("$llmBase/chat/completions")
  $req.Method = "POST"
  $req.ContentType = "application/json; charset=UTF-8"
  $req.Headers.Add("Authorization", "Bearer $llmKey")
  $req.Timeout = 120000; $req.ReadWriteTimeout = 120000
  $b = [Text.Encoding]::UTF8.GetBytes($json)
  $req.ContentLength = $b.Length
  $s = $req.GetRequestStream(); $s.Write($b, 0, $b.Length); $s.Close()
  try { $resp = $req.GetResponse() }
  catch [Net.WebException] { $resp = $_.Exception.Response; if (-not $resp) { throw } }
  $sr = New-Object IO.StreamReader($resp.GetResponseStream(), [Text.Encoding]::UTF8)
  $t = $sr.ReadToEnd(); $sr.Close(); $resp.Close()
  return $t
}

function Send([System.Net.HttpListenerResponse]$res, [int]$code, [string]$text, [string]$type) {
  $bytes = [Text.Encoding]::UTF8.GetBytes($text)
  $res.StatusCode = $code
  $res.ContentType = $type
  $res.ContentLength64 = $bytes.Length
  $res.OutputStream.Write($bytes, 0, $bytes.Length)
  $res.OutputStream.Close()
}

function J($obj) { return ($obj | ConvertTo-Json -Compress -Depth 5) }

$listener = New-Object Net.HttpListener
$listener.Prefixes.Add("http://localhost:$port/")
try { $listener.Start() } catch {
  Write-Host "端口 $port 启动失败：$($_.Exception.Message)"
  Write-Host "可能是已经开了一个窗口在运行，关掉旧窗口再试。"
  Read-Host "按回车退出"; exit 1
}
$url = "http://localhost:$port/"
Write-Host "原作考据侦探已启动：$url"
Write-Host "关掉这个窗口即可停止服务。"
Write-Host ("模型判断：" + $(if ($llmKey) { "已开启（$llmModel）" } else { "未配置，使用规则判定" }))
Start-Process $url

while ($listener.IsListening) {
  $ctx = $listener.GetContext()
  $req = $ctx.Request; $res = $ctx.Response
  $path = $req.Url.AbsolutePath
  try {
    if ($req.HttpMethod -eq "GET" -and ($path -eq "/" -or $path -eq "/index.html")) {
      Send $res 200 ([IO.File]::ReadAllText((Join-Path $dir "index.html"), [Text.Encoding]::UTF8)) "text/html; charset=utf-8"
    }
    elseif ($path -eq "/api/status") {
      Send $res 200 (J @{ key = $true; llm = [bool]$llmKey; model = $llmModel; calls = $script:calls; server = "powershell" }) "application/json; charset=utf-8"
    }
    elseif ($req.HttpMethod -eq "POST" -and $path -eq "/api/search") {
      $sr = New-Object IO.StreamReader($req.InputStream, [Text.Encoding]::UTF8)
      $in = $sr.ReadToEnd() | ConvertFrom-Json
      $body = [ordered]@{ Query = [string]$in.Query }
      if ($in.Mode -ne $null) { $body.Mode = [int]$in.Mode }
      if ($in.Cnt) { $body.Cnt = [int]$in.Cnt }
      if ($in.Site) { $body.Site = [string]$in.Site }
      if ($in.Freshness) { $body.Freshness = [string]$in.Freshness }
      $out = Invoke-YB (J $body)
      Write-Host ("[搜索] " + $body.Query + $(if ($body.Site) { "  @" + $body.Site } else { "" }))
      Send $res 200 $out "application/json; charset=utf-8"
    }
    elseif ($req.HttpMethod -eq "POST" -and $path -eq "/api/llm") {
      if (-not $llmKey) { Send $res 400 '{"error":"没有配置 LLM_API_KEY"}' "application/json; charset=utf-8"; continue }
      $sr = New-Object IO.StreamReader($req.InputStream, [Text.Encoding]::UTF8)
      $in = $sr.ReadToEnd() | ConvertFrom-Json
      $body = [ordered]@{ model = $llmModel; temperature = 0; messages = $in.messages }
      if ($in.max_tokens) { $body.max_tokens = [int]$in.max_tokens }
      if ($in.json) { $body.response_format = @{ type = "json_object" } }
      Write-Host "[模型] $($in.stage)"
      $out = Invoke-LLM ($body | ConvertTo-Json -Compress -Depth 8)
      Send $res 200 $out "application/json; charset=utf-8"
    }
    elseif ($req.HttpMethod -eq "POST" -and $path -eq "/api/save") {
      $sr = New-Object IO.StreamReader($req.InputStream, [Text.Encoding]::UTF8)
      $in = $sr.ReadToEnd() | ConvertFrom-Json
      $name = ([string]$in.name) -replace '[\\/:*?"<>|\s]+', '_'
      if ($name.Length -gt 40) { $name = $name.Substring(0, 40) }
      $stamp = Get-Date -Format "yyyyMMdd-HHmmss"
      $enc = New-Object Text.UTF8Encoding $false
      [IO.File]::WriteAllText((Join-Path $reports "$stamp`_$name.md"), [string]$in.markdown, $enc)
      [IO.File]::WriteAllText((Join-Path $reports "$stamp`_$name.json"), [string]$in.json, $enc)
      if ($in.html) { [IO.File]::WriteAllText((Join-Path $reports "$stamp`_$name.html"), [string]$in.html, $enc) }
      Send $res 200 (J @{ ok = $true; file = "reports\$stamp`_$name.md" }) "application/json; charset=utf-8"
    }
    else { Send $res 404 '{"error":"not found"}' "application/json; charset=utf-8" }
  } catch {
    Write-Host ("出错：" + $_.Exception.Message)
    try { Send $res 500 (J @{ error = $_.Exception.Message }) "application/json; charset=utf-8" } catch {}
  }
}

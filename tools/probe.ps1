$ErrorActionPreference = "Continue"
[Console]::OutputEncoding = [Text.Encoding]::UTF8
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
$dir = Split-Path -Parent $MyInvocation.MyCommand.Path
$key = ""
foreach ($line in [IO.File]::ReadAllLines((Join-Path $dir ".env"), [Text.Encoding]::UTF8)) {
  if ($line -match "^\s*YB_API_KEY\s*=\s*(.+)$") { $key = $Matches[1].Trim() }
}
if (-not $key) { Write-Host "没找到 YB_API_KEY"; exit 1 }
$probes = [IO.File]::ReadAllText((Join-Path $dir "probes.json"), [Text.Encoding]::UTF8) | ConvertFrom-Json
New-Item -ItemType Directory -Force -Path (Join-Path $dir "reports") | Out-Null
$out = @()
foreach ($p in $probes) {
  $body = @{ Query = $p.query; Mode = $p.mode; Cnt = 10 }
  if ($p.site) { $body.Site = $p.site }
  $json = $body | ConvertTo-Json -Compress
  $bytes = [Text.Encoding]::UTF8.GetBytes($json)
  try {
    $r = Invoke-WebRequest -Uri "https://api.wsa.cloud.tencent.com/SearchPro" -Method Post -UseBasicParsing `
         -Headers @{ Authorization = "Bearer $key" } -ContentType "application/json; charset=UTF-8" -Body $bytes -TimeoutSec 30
    $ms = New-Object IO.MemoryStream; $r.RawContentStream.CopyTo($ms)
    $text = [Text.Encoding]::UTF8.GetString($ms.ToArray())
  } catch {
    $text = '{"ps_error":' + (ConvertTo-Json ($_.Exception.Message + " " + $_.ErrorDetails.Message)) + '}'
  }
  Write-Host ("完成: " + $p.label)
  $out += '{"label":' + (ConvertTo-Json $p.label) + ',"query":' + (ConvertTo-Json $p.query) + ',"raw":' + $text + '}'
}
$path = Join-Path $dir "reports\probe_raw.json"
[IO.File]::WriteAllText($path, "[" + ($out -join ",") + "]", (New-Object Text.UTF8Encoding $false))
Write-Host "已写入 $path"

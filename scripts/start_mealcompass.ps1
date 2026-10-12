<#
.SYNOPSIS
    MealCompass 一键启动器（由根目录 start_mealcompass.bat 双击调用）。

.DESCRIPTION
    做三件事：
      1. 启动前自检：Python / Node / pnpm / 后端虚拟环境 / 前端依赖 / 端口占用 / 数据库可达性；
      2. 启动后端（uvicorn）与前端（next dev），日志写入 .tmp\launch\；
      3. 等两个服务真正就绪后，在终端打印可直接点击的网址；起不来时打印日志尾部 + 可执行的排查建议。

    用法（或直接双击 start_mealcompass.bat）：
        start_mealcompass.bat              启动前端 + 后端并打印网址
        start_mealcompass.bat check        只做自检，不启动任何服务
        start_mealcompass.bat status       查看上一次启动的服务是否还活着
        start_mealcompass.bat stop         停止上一次由本脚本启动的服务
        start_mealcompass.bat open         启动并在就绪后自动打开浏览器
        start_mealcompass.bat reload       启动并开启后端热重载（默认关闭）

.PARAMETER Command
    start（默认）/ check / status / stop / open。

.PARAMETER BackendPort
    后端端口，默认 8000（与 README 一致）。

.PARAMETER FrontendPort
    前端端口，默认 3000（与 README 一致）。

.PARAMETER Reload
    后端开启 --reload 热重载（改 Python 代码后自动生效）。默认关闭：
    reload 依赖 multiprocessing 具名管道，受限环境（沙箱 / 安全软件）会直接拒绝而启动失败。

.PARAMETER Open
    服务就绪后自动用默认浏览器打开推荐页。

.NOTES
    停止服务：在本窗口按 Ctrl+C，或直接关闭窗口，或运行 `start_mealcompass.bat stop`。
    即使窗口被直接关闭（Ctrl+C 无法触发清理），下次运行也会自动清理上一次的残留进程。
#>

#Requires -Version 5.1
[CmdletBinding()]
param(
    [Parameter(Position = 0)]
    [ValidateSet('start', 'check', 'status', 'stop', 'open', 'reload')]
    [string]$Command = 'start',

    [int]$BackendPort = 8000,

    [int]$FrontendPort = 3000,

    [switch]$Reload,

    [switch]$Open
)

$ErrorActionPreference = 'Stop'

# --------------------------------------------------------------------------
# 路径与常量
# --------------------------------------------------------------------------
$Root = Split-Path -Parent $PSScriptRoot
$BackendDir = Join-Path $Root 'backend'
$FrontendDir = Join-Path $Root 'frontend'
$VenvPython = Join-Path $BackendDir '.venv\Scripts\python.exe'
$EnvFile = Join-Path $Root '.env'
$ComposeFile = Join-Path $Root 'docker-compose.yml'
$LogDir = Join-Path $Root '.tmp\launch'
$PidFile = Join-Path $LogDir 'pids.json'
$BackendOut = Join-Path $LogDir 'backend.out.log'
$BackendErr = Join-Path $LogDir 'backend.err.log'
$FrontendOut = Join-Path $LogDir 'frontend.out.log'
$FrontendErr = Join-Path $LogDir 'frontend.err.log'

$BackendHealthUrl = "http://127.0.0.1:$BackendPort/health"
$BackendDocsUrl = "http://127.0.0.1:$BackendPort/docs"
$FrontendUrl = "http://localhost:$FrontendPort/recommend"

$script:ProblemCount = 0
$script:WarningCount = 0

# --------------------------------------------------------------------------
# 输出helpers
# --------------------------------------------------------------------------
function Write-Banner {
    param([string]$Text)
    Write-Host ''
    Write-Host ('=' * 62) -ForegroundColor DarkCyan
    Write-Host " $Text" -ForegroundColor Cyan
    Write-Host ('=' * 62) -ForegroundColor DarkCyan
}

function Write-Step {
    param([string]$Text)
    Write-Host ''
    Write-Host "==> $Text" -ForegroundColor Cyan
}

function Write-Ok {
    param([string]$Text)
    Write-Host "  [OK]   $Text" -ForegroundColor Green
}

function Write-Info {
    param([string]$Text)
    Write-Host "  [info] $Text" -ForegroundColor Gray
}

function Write-WarnMsg {
    param([string]$Text)
    $script:WarningCount++
    Write-Host "  [warn] $Text" -ForegroundColor Yellow
}

function Write-FailMsg {
    param([string]$Text)
    $script:ProblemCount++
    Write-Host "  [FAIL] $Text" -ForegroundColor Red
}

# --------------------------------------------------------------------------
# 探测helpers（注意：本环境 Get-NetTCPConnection 不可靠，端口一律用 TCP 直连判定）
# --------------------------------------------------------------------------
function Test-TcpPort {
    param(
        [string]$Target = '127.0.0.1',
        [int]$Port,
        [int]$TimeoutMs = 1200
    )
    $client = New-Object System.Net.Sockets.TcpClient
    try {
        $async = $client.BeginConnect($Target, $Port, $null, $null)
        if (-not $async.AsyncWaitHandle.WaitOne($TimeoutMs)) { return $false }
        $client.EndConnect($async)
        return $true
    }
    catch {
        return $false
    }
    finally {
        try { $client.Close() } catch { }
    }
}

function Test-HttpOk {
    param(
        [string]$Url,
        [int]$TimeoutSec = 5
    )
    try {
        $resp = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec $TimeoutSec -ErrorAction Stop
        return ($resp.StatusCode -ge 200 -and $resp.StatusCode -lt 400)
    }
    catch {
        return $false
    }
}

function Get-PortOwner {
    param([int]$Port)
    $owner = $null
    try {
        $conn = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction Stop |
            Select-Object -First 1
        if ($conn) { $owner = [int]$conn.OwningProcess }
    }
    catch {
        $owner = $null
    }
    if (-not $owner) {
        try {
            $match = netstat -ano | Select-String -Pattern ":$Port\s" |
                Select-String -Pattern 'LISTENING' | Select-Object -First 1
            if ($match) {
                $parts = ($match.Line -split '\s+') | Where-Object { $_ -ne '' }
                $owner = [int]$parts[-1]
            }
        }
        catch {
            $owner = $null
        }
    }
    if ($owner -and $owner -gt 0) { return $owner }
    return $null
}

function Get-ProcessLabel {
    param([int]$ProcessId)
    try {
        $proc = Get-Process -Id $ProcessId -ErrorAction Stop
        return "$($proc.ProcessName) (PID $ProcessId)"
    }
    catch {
        return "PID $ProcessId"
    }
}

function Show-LogTail {
    param(
        [string]$Path,
        [int]$Lines = 20,
        [string]$Title = '日志'
    )
    if (-not (Test-Path $Path)) {
        Write-Info "$Title 不存在：$Path"
        return
    }
    Write-Host "  ---- $Title 最后 $Lines 行（$Path）----" -ForegroundColor DarkGray
    Get-Content -Path $Path -Tail $Lines -ErrorAction SilentlyContinue |
        ForEach-Object { Write-Host "    $_" -ForegroundColor DarkGray }
    Write-Host '  ----------------------------------------' -ForegroundColor DarkGray
}

# --------------------------------------------------------------------------
# 进程管理
# --------------------------------------------------------------------------
function Stop-ProcessTree {
    param(
        [int]$ProcessId,
        [string]$Label = '进程',
        [switch]$Quiet
    )
    if ($ProcessId -le 0) { return $true }
    $alive = Get-Process -Id $ProcessId -ErrorAction SilentlyContinue
    if (-not $alive) { return $true }

    $output = & taskkill.exe /PID $ProcessId /T /F 2>&1
    $ok = ($LASTEXITCODE -eq 0)
    if (-not $ok) {
        # taskkill 偶尔拿不到子进程（或被策略拦），退一步直接杀本体
        try {
            Stop-Process -Id $ProcessId -Force -ErrorAction Stop
            $ok = $true
        }
        catch { $ok = $false }
    }

    if ($ok) {
        if (-not $Quiet) { Write-Info "已停止 $Label（PID $ProcessId）" }
    }
    else {
        Write-WarnMsg "无法停止 $Label（PID $ProcessId）：$($output -join ' ')"
        Write-Info "请手动执行：taskkill /PID $ProcessId /T /F"
    }
    return $ok
}

function Read-PidFile {
    if (-not (Test-Path $PidFile)) { return $null }
    try {
        return (Get-Content $PidFile -Raw | ConvertFrom-Json)
    }
    catch {
        return $null
    }
}

function Get-TrackedProcess {
    param($Record)
    if (-not $Record) { return $null }
    $procId = [int]$Record.pid
    if ($procId -le 0) { return $null }
    return Get-Process -Id $procId -ErrorAction SilentlyContinue
}

function Stop-TrackedServices {
    param([switch]$Quiet)
    $data = Read-PidFile
    if (-not $data) {
        if (-not $Quiet) { Write-Info '没有找到上一次的启动记录，无需清理。' }
        return
    }
    $allStopped = $true
    foreach ($name in @('backend', 'frontend')) {
        $record = $data.$name
        if (-not $record) { continue }
        if ([int]$record.pid -le 0) {
            if (-not $Quiet) { Write-Info "$name 由其他进程提供（本次为复用），本脚本不管理它。" }
            continue
        }
        # 先杀真正占端口的服务进程（node / python），再杀启动它的 cmd 包装进程。
        # 只杀包装进程时，node 可能存活并继续占用端口（实测踩过）。
        $servicePid = [int]$record.pid
        $wrapperPid = 0
        if ($record.PSObject.Properties['wrapperPid']) { $wrapperPid = [int]$record.wrapperPid }

        $found = $false
        if ($servicePid -gt 0 -and (Get-Process -Id $servicePid -ErrorAction SilentlyContinue)) {
            $found = $true
            $ok = Stop-ProcessTree -ProcessId $servicePid -Label "$name 服务" -Quiet:$Quiet
            if (-not $ok) { $allStopped = $false }
        }
        if ($wrapperPid -gt 0 -and (Get-Process -Id $wrapperPid -ErrorAction SilentlyContinue)) {
            $found = $true
            $wrapperOk = Stop-ProcessTree -ProcessId $wrapperPid -Label "$name 包装进程" -Quiet:$Quiet
            if (-not $wrapperOk) { $allStopped = $false }
        }
        if (-not $found -and -not $Quiet) {
            Write-Info "$name 已不在运行（PID $servicePid）。"
        }
    }
    if ($allStopped) {
        Remove-Item $PidFile -Force -ErrorAction SilentlyContinue
    }
    else {
        Write-WarnMsg '有进程未能停止，已保留启动记录（pids.json），下次运行会再次尝试清理。'
    }
    return $allStopped
}

function Save-PidFile {
    param(
        [int]$BackendPid,
        [int]$FrontendPid,
        [int]$BackendWrapperPid = 0,
        [int]$FrontendWrapperPid = 0
    )
    $payload = [ordered]@{
        backend  = [ordered]@{
            pid        = $BackendPid
            wrapperPid = $BackendWrapperPid
            port       = $BackendPort
            startedAt  = (Get-Date).ToString('s')
        }
        frontend = [ordered]@{
            pid        = $FrontendPid
            wrapperPid = $FrontendWrapperPid
            port       = $FrontendPort
            startedAt  = (Get-Date).ToString('s')
        }
    }
    ($payload | ConvertTo-Json -Depth 4) | Set-Content -Path $PidFile -Encoding UTF8
}

# --------------------------------------------------------------------------
# 自检
# --------------------------------------------------------------------------
function Get-DatabaseTarget {
    if (Test-Path $EnvFile) {
        $line = Get-Content $EnvFile -ErrorAction SilentlyContinue |
            Where-Object { $_ -match '^\s*DATABASE_URL\s*=' } | Select-Object -First 1
        if ($line) {
            $url = ($line -split '=', 2)[1].Trim().Trim('"').Trim("'")
            $url = $url -replace '^postgresql\+asyncpg://', 'postgresql://'
            try {
                $uri = New-Object System.Uri($url)
                $port = if ($uri.Port -gt 0) { $uri.Port } else { 5432 }
                return [pscustomobject]@{ Host = $uri.Host; Port = $port }
            }
            catch {
                return [pscustomobject]@{ Host = 'localhost'; Port = 5432 }
            }
        }
    }
    return [pscustomobject]@{ Host = 'localhost'; Port = 5432 }
}

function Try-StartPostgres {
    $docker = Get-Command docker -ErrorAction SilentlyContinue
    if (-not $docker) {
        Write-WarnMsg '未找到 docker 命令，无法自动启动数据库。'
        return $false
    }
    if (-not (Test-Path $ComposeFile)) {
        Write-WarnMsg "未找到 $ComposeFile，无法自动启动数据库。"
        return $false
    }
    Write-Info '尝试自动启动数据库：docker compose up -d postgres'
    try {
        $output = & $docker.Source compose --project-directory $Root up -d postgres 2>&1
        $output | ForEach-Object { Write-Host "    $_" -ForegroundColor DarkGray }
    }
    catch {
        Write-WarnMsg "docker compose 调用失败：$($_.Exception.Message)"
        return $false
    }
    return $true
}

function Invoke-Preflight {
    param([switch]$StartServers)

    Write-Step '环境自检'

    # 1) 目录结构
    if (-not (Test-Path $BackendDir)) { Write-FailMsg "缺少后端目录：$BackendDir" }
    if (-not (Test-Path $FrontendDir)) { Write-FailMsg "缺少前端目录：$FrontendDir" }

    # 2) Python 虚拟环境
    if (-not (Test-Path $VenvPython)) {
        Write-FailMsg "后端虚拟环境不存在：$VenvPython"
        Write-Info '修复：在 backend 目录执行 python -m venv .venv，然后 .venv\Scripts\python.exe -m pip install -r requirements.txt'
    }
    else {
        $pyVersion = (& $VenvPython --version 2>&1) -join ' '
        Write-Ok "后端 Python：$pyVersion"
        $missing = @()
        foreach ($mod in @('uvicorn', 'asyncpg', 'fastapi', 'pydantic')) {
            $probe = & $VenvPython -c "import importlib.util as u; print(1 if u.find_spec('$mod') else 0)" 2>&1
            if ("$probe".Trim() -ne '1') { $missing += $mod }
        }
        if ($missing.Count -gt 0) {
            Write-FailMsg "后端缺少依赖：$($missing -join ', ')"
            Write-Info '修复：backend\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt'
        }
        else {
            Write-Ok '后端依赖齐全（uvicorn / fastapi / pydantic / asyncpg）'
        }
    }

    # 3) Node / pnpm / 前端依赖
    $node = Get-Command node -ErrorAction SilentlyContinue
    if (-not $node) {
        Write-FailMsg '未找到 node，请安装 Node.js 18+（README 要求）。'
    }
    else {
        Write-Ok "Node.js：$(& node --version)"
    }

    $pnpm = Get-Command pnpm -ErrorAction SilentlyContinue
    if (-not $pnpm) {
        Write-FailMsg '未找到 pnpm。'
        Write-Info '修复：corepack enable（Node 16.13+ 自带）或 npm i -g pnpm'
    }
    else {
        Write-Ok "pnpm：$(& pnpm --version)"
    }

    if (-not (Test-Path (Join-Path $FrontendDir 'node_modules'))) {
        Write-FailMsg '前端依赖未安装（缺少 frontend\node_modules）。'
        Write-Info '修复：在 frontend 目录执行 pnpm install'
    }
    else {
        Write-Ok '前端依赖已安装（frontend\node_modules 存在）'
    }

    # 4) 端口
    foreach ($item in @(@{ Name = '后端'; Port = $BackendPort; Url = $BackendHealthUrl },
            @{ Name = '前端'; Port = $FrontendPort; Url = "http://127.0.0.1:$FrontendPort/" })) {
        if (Test-TcpPort -Port $item.Port) {
            if (Test-HttpOk -Url $item.Url -TimeoutSec 3) {
                Write-WarnMsg "$($item.Name)端口 $($item.Port) 已有服务在响应（很可能是上次启动的），本次将直接复用。"
            }
            else {
                $owner = Get-PortOwner -Port $item.Port
                Write-FailMsg "$($item.Name)端口 $($item.Port) 被占用，且不是 MealCompass 服务。"
                if ($owner) { Write-Info "占用进程：$(Get-ProcessLabel -ProcessId $owner)" }
                Write-Info "修复：换端口（-BackendPort / -FrontendPort），或结束占用进程，或运行 start_mealcompass.bat stop"
            }
        }
        else {
            Write-Ok "$($item.Name)端口 $($item.Port) 空闲"
        }
    }

    # 5) .env
    if (Test-Path $EnvFile) {
        Write-Ok '根目录 .env 存在'
    }
    else {
        Write-WarnMsg '根目录没有 .env，后端会用默认配置启动（数据库/LLM key 可能缺失）。'
        Write-Info '修复：复制 .env.example 为 .env 并填写'
    }

    # 6) 数据库可达性（用 TCP 直连判定，不用 Get-NetTCPConnection）
    $db = Get-DatabaseTarget
    Write-Info "数据库目标：$($db.Host):$($db.Port)"
    if (Test-TcpPort -Target $db.Host -Port $db.Port -TimeoutMs 1500) {
        Write-Ok "数据库可达（$($db.Host):$($db.Port)）"
    }
    else {
        Write-WarnMsg "数据库不可达（$($db.Host):$($db.Port)）。"
        if ($StartServers) {
            if (Try-StartPostgres) {
                $deadline = (Get-Date).AddSeconds(45)
                $ready = $false
                while ((Get-Date) -lt $deadline) {
                    if (Test-TcpPort -Target $db.Host -Port $db.Port -TimeoutMs 1500) { $ready = $true; break }
                    Start-Sleep -Seconds 2
                }
                if ($ready) { Write-Ok '数据库已启动并可达' }
                else { Write-WarnMsg '等待数据库超时；前端界面仍会打开，但推荐接口会失败。' }
            }
            else {
                Write-WarnMsg '无法自动启动数据库；前端界面仍会打开，但推荐接口会失败。'
            }
        }
        Write-Info '手动启动：docker compose up -d postgres（或启动本机 PostgreSQL 服务）'
    }

    # 7) 上一次启动的残留
    $previous = Read-PidFile
    if ($previous) {
        $alive = @()
        foreach ($name in @('backend', 'frontend')) {
            $record = $previous.$name
            if ($record -and (Get-TrackedProcess -Record $record)) { $alive += "$name(PID $($record.pid))" }
        }
        if ($alive.Count -gt 0) {
            Write-WarnMsg "检测到上一次启动仍在运行：$($alive -join '、')，本次启动前会先停止它们。"
        }
        else {
            Write-Info '上一次的启动记录已失效，清理记录文件。'
        }
    }
}


function Show-Diagnosis {
    param(
        [string]$Label,
        [string]$OutLog,
        [string]$ErrLog
    )
    Write-Step "$Label 启动失败 · 自动排查"
    Show-LogTail -Path $ErrLog -Lines 25 -Title "$Label stderr"
    Show-LogTail -Path $OutLog -Lines 15 -Title "$Label stdout"

    $text = ''
    foreach ($path in @($ErrLog, $OutLog)) {
        if (Test-Path $path) {
            $text += ((Get-Content -Path $path -Tail 60 -ErrorAction SilentlyContinue) -join "`n")
        }
    }

    $hints = New-Object System.Collections.Generic.List[string]
    if ($text -match 'Address already in use|EADDRINUSE|10048') {
        $hints.Add('端口被占用：换个端口（-BackendPort / -FrontendPort），或先运行 start_mealcompass.bat stop。')
    }
    if ($text -match 'ModuleNotFoundError|No module named|Cannot find module') {
        $hints.Add('缺少依赖：后端 .venv\Scripts\python.exe -m pip install -r backend\requirements.txt；前端在 frontend 里 pnpm install。')
    }
    if ($text -match 'ConnectionRefusedError|connection refused|asyncpg|could not connect|password authentication') {
        $hints.Add('数据库连不上：先 docker compose up -d postgres，确认 .env 的 DATABASE_URL 指向的地址与端口可用。')
    }
    if ($text -match 'function .* does not exist') {
        $hints.Add('数据库结构与代码不一致：确认数据库已完成迁移/灌数据（见 README 的初始化步骤）。')
    }
    if ($text -match 'EPERM|EACCES|Access is denied') {
        $hints.Add('权限被拒绝：可能是杀软或沙箱拦截子进程/管道；把仓库目录加入白名单后重试。')
    }
    if ($text -match 'CreateNamedPipe|resource_sharer|WinError 5') {
        $hints.Add('具名管道被拒：后端 --reload 需要 multiprocessing 管道；去掉 reload（本脚本默认关闭）重试。')
    }
    if ($text -match 'ValidationError|Invalid environment variable') {
        $hints.Add('配置有问题：检查根目录 .env 的取值格式（尤其 CORS_ALLOW_ORIGINS 需为 JSON 数组）。')
    }
    if ($text -match 'ECONNREFUSED|ENOTFOUND|ETIMEDOUT|ReadTimeout|ConnectError') {
        $hints.Add('外部服务（SiliconFlow / Langfuse）连不上：检查网络与 key；后端有本地降级路径，但检索质量会下降。')
    }
    if ($hints.Count -eq 0) {
        $hints.Add("仔细看上面的日志尾部；完整日志：$OutLog 与 $ErrLog（可用 -Command check 复跑自检）。")
    }

    Write-Host '  可能原因与修复建议：' -ForegroundColor Yellow
    $i = 1
    foreach ($hint in $hints) {
        Write-Host "    $i) $hint" -ForegroundColor Yellow
        $i++
    }
}

function Resolve-LogPath {
    <#
        上一次的进程可能还活着并占着日志文件（cmd 的 `>` 重定向会失败，
        命令随即以 1 退出——实测踩过）。这里先试探能否独占写入；
        写不了就换一个带时间戳的文件名，保证启动本身不受影响。
    #>
    param([string]$PreferredPath)
    try {
        $stream = [System.IO.File]::Open($PreferredPath, 'Create', 'Write', 'None')
        $stream.Close()
        return $PreferredPath
    }
    catch {
        $dir = Split-Path -Parent $PreferredPath
        $name = [System.IO.Path]::GetFileNameWithoutExtension($PreferredPath)
        $ext = [System.IO.Path]::GetExtension($PreferredPath)
        $alt = Join-Path $dir ($name + '-' + (Get-Date -Format 'HHmmss') + $ext)
        Write-WarnMsg "日志文件被别的进程占用（很可能是上一次的服务还在写）：$PreferredPath"
        Write-Info "本次改用：$alt"
        return $alt
    }
}

# --------------------------------------------------------------------------
# 启动
# --------------------------------------------------------------------------
function Get-ExitCodeText {
    param([System.Diagnostics.Process]$Process)
    if (-not $Process) { return 'unknown' }
    try {
        [void]$Process.WaitForExit(1000)
        return "$($Process.ExitCode)"
    }
    catch {
        return 'unknown'
    }
}

function Start-LoggedProcess {
    <#
        用 .NET 直接启动 cmd /s /c "<命令> > out 2> err"。
        为什么不用 Start-Process -PassThru -NoNewWindow：本机 pwsh 7.6 下它返回的
        Process 对象 ExitCode 恒为空（实测），会让"构建是否成功"这类判断全部失效。
        UseShellExecute=false + CreateNoWindow=false 保留控制台继承（关窗口即停子进程），
        同时 ExitCode 可读（实测 exit 7 能正确读回 7）。
    #>
    param(
        [string]$CommandLine,
        [string]$WorkingDirectory,
        [string]$OutLog,
        [string]$ErrLog,
        [switch]$BlockUntilExit
    )
    $outPath = Resolve-LogPath -PreferredPath $OutLog
    $errPath = Resolve-LogPath -PreferredPath $ErrLog
    $script:LastOutLog = $outPath
    $script:LastErrLog = $errPath
    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = 'cmd.exe'
    $psi.Arguments = '/s /c "' + $CommandLine + ' > "' + $outPath + '" 2> "' + $errPath + '""'
    $psi.WorkingDirectory = $WorkingDirectory
    $psi.UseShellExecute = $false
    $psi.CreateNoWindow = $false
    $proc = [System.Diagnostics.Process]::Start($psi)
    if ($BlockUntilExit) {
        $proc.WaitForExit()
        Write-Info "退出码：$($proc.ExitCode)"
    }
    return $proc
}

function Start-Backend {
    param([int]$Port)
    Write-Step "启动后端（uvicorn，端口 $Port）"
    if (Test-TcpPort -Port $Port -and (Test-HttpOk -Url $BackendHealthUrl -TimeoutSec 3)) {
        Write-Ok "后端已在运行（端口 $Port 有健康响应），复用现有进程。"
        return $null
    }
    $uvicornArgs = @('-m', 'uvicorn', 'main:app', '--host', '127.0.0.1', '--port', "$Port")
    if ($Reload) { $uvicornArgs += '--reload' }
    $commandLine = '"' + $VenvPython + '" ' + ($uvicornArgs -join ' ')
    Write-Info "命令：$commandLine"
    $proc = Start-LoggedProcess -CommandLine $commandLine -WorkingDirectory $BackendDir `
        -OutLog $BackendOut -ErrLog $BackendErr
    Write-Info "后端日志：$script:LastOutLog / $script:LastErrLog"
    return $proc
}

function Start-FrontendDev {
    param([int]$Port)
    Write-Step "启动前端（next dev，端口 $Port）"
    if (Test-TcpPort -Port $Port -and (Test-HttpOk -Url "http://127.0.0.1:$Port/" -TimeoutSec 5)) {
        Write-Ok "前端已在运行（端口 $Port 有响应），复用现有进程。"
        return $null
    }
    $proc = Start-LoggedProcess -CommandLine 'pnpm dev' -WorkingDirectory $FrontendDir `
        -OutLog $FrontendOut -ErrLog $FrontendErr
    Write-Info "前端日志：$script:LastOutLog / $script:LastErrLog"
    return $proc
}

function Test-FrontendForkBlocked {
    # `next dev` 必须 fork 一个带 IPC 具名管道的子进程（next-dev.js 的 startServer）。
    # 受限环境（沙箱 / 安全软件）会直接报 spawn EPERM；`next start` 在同进程内启动，不受影响。
    foreach ($path in @($FrontendErr, $FrontendOut)) {
        if (Test-Path $path) {
            $text = Get-Content -Path $path -Raw -ErrorAction SilentlyContinue
            if ($text -match 'spawn EPERM') { return $true }
        }
    }
    return $false
}

function Build-Frontend {
    param(
        [string]$LogPath,
        [string]$ErrPath
    )
    Write-Info '正在构建前端生产包（pnpm build，本机约 30-60 秒）...'
    $proc = Start-LoggedProcess -CommandLine 'pnpm build' -WorkingDirectory $FrontendDir `
        -OutLog $LogPath -ErrLog $ErrPath -BlockUntilExit
    return ($proc.ExitCode -eq 0)
}

function Start-FrontendProd {
    param(
        [int]$Port,
        [string]$LogPath,
        [string]$ErrPath
    )
    Write-Step "启动前端（next start 生产模式，端口 $Port）"
    # 直接用 node_modules 里的 next 可执行文件：`pnpm start -- -p 3000` 会被 pnpm 把
    # "--" 原样透传给 next，next 把它当成项目目录，报 "no such directory: ...\-p"。
    $nextBin = Join-Path $FrontendDir 'node_modules\.bin\next.cmd'
    $proc = Start-LoggedProcess -CommandLine ('"' + $nextBin + '" start -p ' + $Port) `
        -WorkingDirectory $FrontendDir -OutLog $LogPath -ErrLog $ErrPath
    Write-Info "前端日志：$script:LastOutLog / $script:LastErrLog"
    return $proc
}

function Wait-BackendReady {
    param(
        [System.Diagnostics.Process]$Process,
        [int]$TimeoutSec = 60
    )
    $deadline = (Get-Date).AddSeconds($TimeoutSec)
    while ((Get-Date) -lt $deadline) {
        if ($Process -and $Process.HasExited) { return $false }
        if (Test-HttpOk -Url $BackendHealthUrl -TimeoutSec 3) { return $true }
        Start-Sleep -Milliseconds 800
    }
    return $false
}

function Wait-FrontendReady {
    param(
        [System.Diagnostics.Process]$Process,
        [int]$Port,
        [int]$TimeoutSec = 150
    )
    $deadline = (Get-Date).AddSeconds($TimeoutSec)
    while ((Get-Date) -lt $deadline) {
        if ($Process -and $Process.HasExited) { return $false }
        if (Test-TcpPort -Port $Port) {
            # 端口通了之后再打一次请求，触发 Next 首次编译（失败也不影响端口就绪判定）
            [void](Test-HttpOk -Url "http://127.0.0.1:$Port/" -TimeoutSec 20)
            return $true
        }
        Start-Sleep -Milliseconds 800
    }
    return $false
}

function Show-Urls {
    param(
        [int]$BackendPortValue,
        [int]$FrontendPortValue,
        [string]$FrontendMode = 'dev'
    )
    Write-Host ''
    Write-Host ('=' * 62) -ForegroundColor Green
    Write-Host ' MealCompass 已就绪' -ForegroundColor Green
    Write-Host ('=' * 62) -ForegroundColor Green
    Write-Host ''
    Write-Host '  推荐页面   ' -NoNewline -ForegroundColor White
    Write-Host "http://localhost:$FrontendPortValue/recommend" -ForegroundColor Cyan
    Write-Host '  首页       ' -NoNewline -ForegroundColor White
    Write-Host "http://localhost:$FrontendPortValue" -ForegroundColor Cyan
    Write-Host '  后端 API   ' -NoNewline -ForegroundColor White
    Write-Host "http://localhost:$BackendPortValue/docs" -ForegroundColor Cyan
    Write-Host '  健康检查   ' -NoNewline -ForegroundColor White
    Write-Host "http://localhost:$BackendPortValue/health" -ForegroundColor Cyan
    Write-Host ''
    if ($FrontendMode -eq 'production') {
        Write-Host '  前端模式：生产（dev 的 fork 被环境拒绝，已自动降级；无热重载）' -ForegroundColor DarkYellow
    }
    else {
        Write-Host '  前端模式：开发（热重载已开启）' -ForegroundColor DarkGray
    }
    Write-Host '  停止服务：在本窗口按 Ctrl+C，或直接关闭窗口，或运行 start_mealcompass.bat stop' -ForegroundColor DarkGray
    Write-Host '  日志目录：.tmp\launch\' -ForegroundColor DarkGray
    Write-Host ''
}

function Show-Status {
    Write-Banner 'MealCompass 服务状态'
    $data = Read-PidFile

    Write-Step '端口探测（TCP 直连）'
    if (Test-TcpPort -Port $BackendPort) {
        $health = if (Test-HttpOk -Url $BackendHealthUrl -TimeoutSec 3) { '健康检查通过' } else { '端口通，但 /health 无响应' }
        Write-Ok "后端端口 $BackendPort 在监听（$health）"
    }
    else {
        Write-Info "后端端口 $BackendPort 空闲（未运行）"
    }
    if (Test-TcpPort -Port $FrontendPort) {
        Write-Ok "前端端口 $FrontendPort 在监听"
    }
    else {
        Write-Info "前端端口 $FrontendPort 空闲（未运行）"
    }

    Write-Step '本脚本的启动记录'
    if (-not $data) {
        Write-Info '没有启动记录（可能不是本脚本启动的，或已运行 stop）。'
        return
    }
    foreach ($name in @('backend', 'frontend')) {
        $record = $data.$name
        if (-not $record) { continue }
        if ([int]$record.pid -le 0) {
            Write-Info "$name 由其他进程提供（本次为复用），本脚本不管理它。"
            continue
        }
        $proc = Get-TrackedProcess -Record $record
        if ($proc) {
            Write-Ok "$name 仍在运行：$(Get-ProcessLabel -ProcessId ([int]$record.pid))，端口 $($record.port)"
        }
        else {
            Write-Info "$name 已停止（记录 PID $($record.pid)，启动于 $($record.startedAt)）"
        }
    }
}

# --------------------------------------------------------------------------
# 主流程
# --------------------------------------------------------------------------
if (-not (Test-Path $LogDir)) {
    New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
}

if ($Command -eq 'status') {
    Show-Status
    exit 0
}

if ($Command -eq 'stop') {
    Write-Banner 'MealCompass 停止服务'
    [void](Stop-TrackedServices)
    Write-Host ''
    Write-Ok '完成。'
    exit 0
}

if ($Command -eq 'check') {
    Write-Banner 'MealCompass 自检（不启动服务）'
    Write-Info "仓库：$Root"
    Invoke-Preflight
    Write-Host ''
    if ($script:ProblemCount -gt 0) {
        Write-FailMsg "自检发现 $($script:ProblemCount) 个必须修复的问题、$($script:WarningCount) 个警告。"
        exit 1
    }
    Write-Ok "自检通过（警告 $($script:WarningCount) 个）。"
    exit 0
}

# Command = start | open
$OpenBrowser = $Open -or ($Command -eq 'open')
if ($Command -eq 'reload') { $Reload = $true }

Write-Banner 'MealCompass 一键启动'
Write-Info "仓库：$Root"
Write-Info "端口：后端 $BackendPort / 前端 $FrontendPort"

Invoke-Preflight -StartServers

if ($script:ProblemCount -gt 0) {
    Write-Host ''
    Write-FailMsg "自检未通过（$($script:ProblemCount) 个问题），已停止启动。修复后重试，或运行 start_mealcompass.bat check 只看自检。"
    exit 1
}

# 清理上一次的残留（避免端口冲突）
$previous = Read-PidFile
if ($previous) {
    $anyAlive = $false
    foreach ($name in @('backend', 'frontend')) {
        $record = $previous.$name
        if ($record -and (Get-TrackedProcess -Record $record)) { $anyAlive = $true }
    }
    if ($anyAlive) {
        Write-Step '清理上一次启动的残留进程'
        Stop-TrackedServices -Quiet
    }
    else {
        Remove-Item $PidFile -Force -ErrorAction SilentlyContinue
    }
}

$backendProc = $null
$frontendProc = $null
$backendPid = 0
$frontendPid = 0
$backendWrapperPid = 0
$frontendWrapperPid = 0
$frontendMode = 'dev'
$frontendBuildOut = Join-Path $LogDir 'frontend.build.out.log'
$frontendBuildErr = Join-Path $LogDir 'frontend.build.err.log'

try {
    $backendProc = Start-Backend -Port $BackendPort
    if ($script:LastOutLog) { $BackendOut = $script:LastOutLog; $BackendErr = $script:LastErrLog }
    if ($backendProc) {
        $backendWrapperPid = $backendProc.Id
        $backendPid = $backendProc.Id
    }
    else {
        $record = (Read-PidFile).backend
        if ($record) { $backendPid = [int]$record.pid }
    }

    if ($backendProc) {
        Write-Info '等待后端健康检查...'
        if (-not (Wait-BackendReady -Process $backendProc -TimeoutSec 60)) {
            if ($backendProc.HasExited) {
                Write-FailMsg "后端进程已退出（退出码 $(Get-ExitCodeText -Process $backendProc)）。"
            }
            else {
                Write-FailMsg '等待后端健康检查超时（60 秒）。'
            }
            Show-Diagnosis -Label '后端' -OutLog $BackendOut -ErrLog $BackendErr
            Write-Host ''
            Write-Host '  按 Enter 关闭窗口...' -ForegroundColor Yellow
            [void](Read-Host)
            exit 1
        }
        Write-Ok '后端健康检查通过'
        # 真正占端口的是 uvicorn 的 python 进程（与 cmd 包装进程可能不是同一个），
        # 记录端口所有者，stop 时才能停干净。
        $owner = Get-PortOwner -Port $BackendPort
        if ($owner) { $backendPid = $owner }
    }

    $frontendProc = Start-FrontendDev -Port $FrontendPort
    if ($script:LastOutLog) { $FrontendOut = $script:LastOutLog; $FrontendErr = $script:LastErrLog }
    if ($frontendProc) {
        $frontendWrapperPid = $frontendProc.Id
        $frontendPid = $frontendProc.Id
    }

    if ($frontendProc) {
        Write-Info '等待前端端口就绪（首次编译可能较慢）...'
        $ready = Wait-FrontendReady -Process $frontendProc -Port $FrontendPort -TimeoutSec 150

        # dev 模式失败且原因是 fork 被拒（具名管道受限）时，自动降级到生产模式。
        # `next start` 在同进程内启动，不 fork，功能一致，只是没有热重载。
        if (-not $ready -and (Test-FrontendForkBlocked)) {
            Write-Host ''
            Write-WarnMsg 'next dev 需要 fork 带 IPC 具名管道的子进程，当前环境拒绝了这个操作（spawn EPERM）。'
            Write-WarnMsg '自动切换到生产模式（pnpm build + pnpm start）：功能一致，但没有热重载。'
            if (Test-TcpPort -Port $FrontendPort) {
                # dev 失败后可能留下半个进程
                Stop-ProcessTree -ProcessId $frontendPid -Label '前端(dev)' -Quiet
            }
            $hasBuild = Test-Path (Join-Path $FrontendDir '.next\BUILD_ID')
            if (-not $hasBuild) {
                if (-not (Build-Frontend -LogPath $frontendBuildOut -ErrPath $frontendBuildErr)) {
                    Write-FailMsg '前端生产构建失败。'
                    Show-Diagnosis -Label '前端构建' -OutLog $script:LastOutLog -ErrLog $script:LastErrLog
                    Write-Host ''
                    Write-Host '  按 Enter 关闭窗口...' -ForegroundColor Yellow
                    [void](Read-Host)
                    exit 1
                }
                Write-Ok '前端生产构建完成'
            }
            else {
                Write-Info '沿用已有生产构建（frontend\.next\BUILD_ID）；如需刷新请在 frontend 里执行 pnpm build。'
            }
            $frontendProc = Start-FrontendProd -Port $FrontendPort -LogPath $FrontendOut -ErrPath $FrontendErr
            if ($script:LastOutLog) { $FrontendOut = $script:LastOutLog; $FrontendErr = $script:LastErrLog }
            $frontendWrapperPid = $frontendProc.Id
            $frontendPid = $frontendProc.Id
            Write-Info '等待前端端口就绪（生产模式）...'
            $ready = Wait-FrontendReady -Process $frontendProc -Port $FrontendPort -TimeoutSec 90
            if ($ready) { $frontendMode = 'production' }
        }

        if (-not $ready) {
            if ($frontendProc.HasExited) {
                Write-FailMsg "前端进程已退出（退出码 $(Get-ExitCodeText -Process $frontendProc)）。"
            }
            else {
                Write-FailMsg '等待前端端口就绪超时。'
            }
            Show-Diagnosis -Label '前端' -OutLog $FrontendOut -ErrLog $FrontendErr
            Write-Host ''
            Write-Host '  按 Enter 关闭窗口...' -ForegroundColor Yellow
            [void](Read-Host)
            exit 1
        }
        Write-Ok "前端端口已就绪（$frontendMode 模式）"
        $owner = Get-PortOwner -Port $FrontendPort
        if ($owner) { $frontendPid = $owner }
    }

    Save-PidFile -BackendPid $backendPid -FrontendPid $frontendPid `
        -BackendWrapperPid $backendWrapperPid -FrontendWrapperPid $frontendWrapperPid

    Show-Urls -BackendPortValue $BackendPort -FrontendPortValue $FrontendPort -FrontendMode $frontendMode

    if ($OpenBrowser) {
        Write-Info "打开浏览器：$FrontendUrl"
        try { Start-Process $FrontendUrl | Out-Null } catch { Write-WarnMsg "自动打开浏览器失败：$($_.Exception.Message)" }
    }

    Write-Host '  正在监视服务（按 Ctrl+C 停止并退出）...' -ForegroundColor DarkGray

    $reportedBackend = $false
    $reportedFrontend = $false
    while ($true) {
        Start-Sleep -Seconds 3

        if ($backendProc -and $backendProc.HasExited -and -not $reportedBackend) {
            $reportedBackend = $true
            Write-Host ''
            Write-FailMsg "后端已退出（退出码 $(Get-ExitCodeText -Process $backendProc)）。"
            Show-Diagnosis -Label '后端' -OutLog $BackendOut -ErrLog $BackendErr
        }
        if ($frontendProc -and $frontendProc.HasExited -and -not $reportedFrontend) {
            $reportedFrontend = $true
            Write-Host ''
            Write-FailMsg "前端已退出（退出码 $(Get-ExitCodeText -Process $frontendProc)）。"
            Show-Diagnosis -Label '前端' -OutLog $FrontendOut -ErrLog $FrontendErr
        }

        $backendGone = (-not $backendProc) -or $backendProc.HasExited
        $frontendGone = (-not $frontendProc) -or $frontendProc.HasExited
        if ($backendGone -and $frontendGone) { break }
    }

    Write-Host ''
    Write-WarnMsg '两个服务都已退出。生产日志仍在 .tmp\launch\ 下。'
}
finally {
    Write-Host ''
    Write-Step '收尾：停止本次启动的服务'
    foreach ($item in @(
            @{ Label = '后端服务'; Pid = $backendPid },
            @{ Label = '后端包装进程'; Pid = $backendWrapperPid },
            @{ Label = '前端服务'; Pid = $frontendPid },
            @{ Label = '前端包装进程'; Pid = $frontendWrapperPid }
        )) {
        if ($item.Pid -gt 0) {
            [void](Stop-ProcessTree -ProcessId $item.Pid -Label $item.Label)
        }
    }
    Remove-Item $PidFile -Force -ErrorAction SilentlyContinue
    Write-Ok '已退出。'
}

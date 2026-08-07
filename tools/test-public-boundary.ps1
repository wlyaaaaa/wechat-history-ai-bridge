param(
    [string] $RepoRoot = (Split-Path -Parent $PSScriptRoot)
)

$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

function Fail([string] $Message) {
    Write-Host "[FAIL] $Message" -ForegroundColor Red
    exit 1
}

function Pass([string] $Message) {
    Write-Host "[ OK ] $Message" -ForegroundColor Green
}

function Get-GitOutput([string[]] $Arguments) {
    $output = & git -C $RepoRoot @Arguments
    if ($LASTEXITCODE -ne 0) {
        Fail "git $($Arguments -join ' ') failed"
    }
    return @($output)
}

if (-not (Test-Path -LiteralPath $RepoRoot -PathType Container)) {
    Fail "RepoRoot does not exist: $RepoRoot"
}

$trackedFiles = Get-GitOutput @('ls-files')
if (-not $trackedFiles) {
    Fail "git ls-files returned no tracked files"
}

$forbiddenTrackedPathPatterns = @(
    '(^|/)\.env($|\.)',
    '(^|/)api-media/',
    '(^|/)exports/',
    '(^|/)dump/',
    '(^|/)screenshots?/',
    '(^|/)media/',
    '(^|/)chatlab[^/]*\.json$',
    '(^|/)messages[^/]*\.json$',
    '\.db$',
    '\.sqlite$',
    '\.sqlite3$',
    '\.db-wal$',
    '\.db-shm$',
    '\.sqlite-wal$',
    '\.sqlite-shm$',
    '\.png$',
    '\.jpg$',
    '\.jpeg$',
    '\.webp$',
    '\.gif$',
    '\.mp4$',
    '\.mov$',
    '\.m4a$',
    '\.mp3$',
    '\.wav$'
)

$allowedBinaryDocs = @(
    'AGENTS.pdf',
    'README.pdf',
    'WATCHDOG.pdf'
)

foreach ($file in $trackedFiles) {
    $normalized = $file -replace '\\', '/'
    if ($normalized -eq '.env.example') {
        continue
    }
    if ($allowedBinaryDocs -contains $normalized) {
        continue
    }
    foreach ($pattern in $forbiddenTrackedPathPatterns) {
        if ($normalized -match $pattern) {
            Fail "tracked private path matched '$pattern': $file"
        }
    }
}
Pass "tracked path boundary"

$expectedIgnoredPaths = @(
    '.env',
    '.env.local',
    'logs/weflow_heartbeat.log',
    'exports/sample.json',
    'api-media/sample.bin',
    'dump/sample.json',
    'sample.db',
    'sample.sqlite',
    'sample.sqlite3',
    'sample.db-wal',
    'sample.sqlite-shm',
    'private-snapshot-synthetic/manifest.json',
    'private-snapshot-synthetic/files.jsonl',
    'private-snapshot-synthetic/readback-receipt.json',
    'private-snapshot-synthetic.incomplete/progress.json'
)

foreach ($path in $expectedIgnoredPaths) {
    & git -C $RepoRoot check-ignore -q -- $path
    if ($LASTEXITCODE -ne 0) {
        Fail "git check-ignore did not ignore expected private path: $path"
    }
}
Pass "gitignore private output boundary"

$expectedNotIgnoredPaths = @(
    'tools/build_private_snapshot_manifest.py',
    'tests/test_private_snapshot_manifest.py'
)

foreach ($path in $expectedNotIgnoredPaths) {
    & git -C $RepoRoot check-ignore -q -- $path
    if ($LASTEXITCODE -eq 0) {
        Fail "gitignore unexpectedly ignores source or test path: $path"
    }
    if ($LASTEXITCODE -ne 1) {
        Fail "git check-ignore failed for expected non-ignored path: $path"
    }
}
Pass "gitignore preserves snapshot tool and tests"

$sensitiveEnvKeys = @(
    'WEFLOW_TOKEN',
    'WEFLOW_DB_KEY'
)

$documentedPrivateGlobs = @(
    '*.sqlite',
    '*.sqlite3',
    '*.db-wal',
    '*.sqlite-shm',
    '*.png',
    '*.jpg',
    '*.webp',
    '*.mp4',
    '*.m4a',
    'chatlab*.json',
    'messages*.json'
)

$secretPatterns = @(
    '-----BEGIN [A-Z ]*PRIVATE KEY-----',
    'ghp_[A-Za-z0-9]{36}',
    'xox[bapr]-[0-9]+-[0-9]+-[A-Za-z0-9]+',
    'sk-[A-Za-z0-9_-]{20,}',
    'wxid_[A-Za-z0-9_-]{8,}',
    '\d+@chatroom'
)

$textExtensions = @(
    '.md', '.json', '.yaml', '.yml', '.ps1', '.vbs', '.py', '.txt', '.example', '.gitignore'
)

foreach ($file in $trackedFiles) {
    $fullPath = Join-Path $RepoRoot $file
    if (-not (Test-Path -LiteralPath $fullPath -PathType Leaf)) {
        continue
    }

    $extension = [System.IO.Path]::GetExtension($fullPath)
    if ($textExtensions -notcontains $extension -and $file -ne '.gitignore') {
        continue
    }

    $content = ''
    try {
        $content = Get-Content -LiteralPath $fullPath -Raw -Encoding UTF8
    } catch {
        continue
    }

    foreach ($pattern in $secretPatterns) {
        if ($content -match $pattern) {
            Fail "tracked text file '$file' matched sensitive pattern '$pattern'"
        }
    }

    foreach ($key in $sensitiveEnvKeys) {
        if ($content -match "(?m)^\s*$key\s*=") {
            if ($file -eq '.env.example' -and $content -match "(?m)^\s*$key\s*=\s*(__FILL_ME__)?\s*$") {
                continue
            }
            Fail "tracked text file '$file' contains sensitive env assignment for $key"
        }
    }
}
Pass "tracked text high-confidence secret scan"

$pdfTool = Get-Command pdftotext -ErrorAction SilentlyContinue
if ($pdfTool) {
    $pdfFiles = $trackedFiles | Where-Object { $_ -match '\.pdf$' }
    foreach ($file in $pdfFiles) {
        $fullPath = Join-Path $RepoRoot $file
        $tempPath = [System.IO.Path]::GetTempFileName()
        try {
            & $pdfTool.Source $fullPath $tempPath 2>$null
            if ($LASTEXITCODE -eq 0 -and (Test-Path -LiteralPath $tempPath)) {
                $content = Get-Content -LiteralPath $tempPath -Raw -Encoding UTF8
                foreach ($pattern in $secretPatterns) {
                    if ($content -match $pattern) {
                        Fail "PDF text '$file' matched sensitive pattern '$pattern'"
                    }
                }
            }
        } finally {
            if (Test-Path -LiteralPath $tempPath) {
                Remove-Item -LiteralPath $tempPath -Force
            }
        }
    }
    Pass "PDF text scan through pdftotext"
} else {
    $pdfFiles = @($trackedFiles | Where-Object { $_ -match '^(README|AGENTS|WATCHDOG)\.pdf$' })
    if ($env:GITHUB_ACTIONS -eq 'true' -and $pdfFiles.Count -gt 0) {
        Fail "pdftotext not found in CI while tracked PDFs exist: $($pdfFiles -join ', ')"
    }
    Write-Host "[SKIP] pdftotext not found; PDF text scan skipped for README.pdf, AGENTS.pdf, WATCHDOG.pdf" -ForegroundColor Yellow
}

$parseTargets = @(
    'probe-weflow.ps1',
    'weflow_heartbeat.ps1',
    'weflow_boot_guardian.ps1',
    'enable-autologin.ps1',
    'tools/test-public-boundary.ps1',
    'tools/test-ci-local.ps1'
)

foreach ($target in $parseTargets) {
    $path = Join-Path $RepoRoot $target
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
        Fail "PowerShell parse target is missing: $target"
    }

    $tokens = $null
    $parseErrors = $null
    $scriptText = Get-Content -LiteralPath $path -Raw -Encoding UTF8
    [System.Management.Automation.Language.Parser]::ParseInput($scriptText, [ref] $tokens, [ref] $parseErrors) | Out-Null
    if ($parseErrors.Count -gt 0) {
        Fail "PowerShell parser found errors in ${target}: $($parseErrors[0].Message)"
    }
}
Pass "PowerShell parser coverage"

Pass "public boundary checks complete"
$global:LASTEXITCODE = 0

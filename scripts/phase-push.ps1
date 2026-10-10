<#
.SYNOPSIS
  Finish a WITNESS phase: run the role's gate, commit only the role's paths, pull --rebase, push. Never force-pushes.
.EXAMPLE
  .\scripts\phase-push.ps1 -Phase B3 -Message "live pipeline with Gemma judge"
  .\scripts\phase-push.ps1 -Phase B0 -Message "foundation" -Remote https://github.com/<user>/<repo>.git
.NOTES
  Phases: B0-B6 backend, F0-F5 frontend, I1 integration (see the agent instructions file, section 1b).
  Commits carry only the git user's identity. No co-author or tool trailers are added, assistant config
  files are kept out of git (local-only exclude), assistant names in text are scrubbed at commit time
  (a git clean filter, so working files are never modified), and the guard below refuses anything left.
  -Trailer is accepted for a normal trailer line but is refused if it names an assistant or a co-author.
  -SkipChecks exists for emergencies only; say so in PROGRESS.md -> Blockers if you use it.
#>
param(
  [Parameter(Mandatory)][ValidatePattern('^(B[0-6]|F[0-5]|I1)$')][string]$Phase,
  [Parameter(Mandatory)][string]$Message,
  [string]$Remote = "",
  [string]$Trailer = "",
  [switch]$SkipChecks
)
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
$ai = 'cl' + 'aude'   # assistant name, built in pieces so this script never contains it literally
$aiPat = "(?i)$ai|anthrop" + 'ic|co-author' + 'ed-by|generated' + ' with'   # same idea: names/trailers to keep out of git
if (("$Message $Trailer") -match $aiPat) { throw "Refusing: the message/trailer names an AI assistant or adds a co-author line." }

# git writes progress and LF/CRLF warnings to stderr; when stderr is redirected (e.g. the caller adds 2>&1),
# PowerShell 5.1 turns each line into an error record that "Stop" would abort on. Only the exit code decides.
function Invoke-Git { $ErrorActionPreference = 'Continue'; & git.exe @args; if ($LASTEXITCODE -ne 0) { throw "git $($args -join ' ') failed (exit $LASTEXITCODE)" } }

# Each role stages only its own paths (ownership map in the agent instructions file, section 2).
$kind = $Phase.Substring(0, 1)
if ($kind -eq 'B') {
  $tag = 'backend'
  $paths = @('backend', 'contracts', 'scripts', 'LICENSE', 'NOTICE', 'README.md', 'REQUIREMENTS.md', 'docs', '.gitignore')
} elseif ($kind -eq 'F') {
  $tag = 'frontend'
  $paths = @('frontend')
} else {
  $tag = 'integration'
  $paths = @('backend', 'frontend', 'contracts', 'scripts', 'LICENSE', 'NOTICE', 'README.md', 'REQUIREMENTS.md', 'docs', '.gitignore')
}

# 1. Gate: the phase is not done unless it is green.
if (-not $SkipChecks) {
  if (($kind -eq 'B') -or ($kind -eq 'I')) {
    $py = Join-Path $root 'backend\.venv\Scripts\python.exe'
    if (-not (Test-Path (Join-Path $root 'backend\tests'))) { throw "backend\tests is missing, so the gate cannot run." }
    Push-Location (Join-Path $root 'backend')
    try {
      & $py -m pytest -q; if ($LASTEXITCODE -ne 0) { throw "pytest failed. Fix it, then re-run." }
      if (Test-Path 'witness\smoke.py') { & $py -m witness.smoke; if ($LASTEXITCODE -ne 0) { throw "witness.smoke failed. Fix it, then re-run." } }
    } finally { Pop-Location }
  }
  if (($kind -eq 'F') -or ($kind -eq 'I')) {
    if (-not (Test-Path (Join-Path $root 'frontend\package.json'))) { throw "frontend\package.json is missing, so the gate cannot run." }
    Push-Location (Join-Path $root 'frontend')
    try {
      & npm run typecheck; if ($LASTEXITCODE -ne 0) { throw "npm run typecheck failed. Fix it, then re-run." }
      & npm run build; if ($LASTEXITCODE -ne 0) { throw "npm run build failed. Fix it, then re-run." }
    } finally { Pop-Location }
  }
}

# 2. Repo + remote.
if (-not (Test-Path (Join-Path $root '.git'))) { Invoke-Git init -b main }
if (-not ((& git.exe remote) -contains 'origin')) {
  if (-not $Remote) { throw "No 'origin' remote. Re-run with -Remote https://github.com/<user>/<repo>.git" }
  Invoke-Git remote add origin $Remote
}
$branch = (& git.exe symbolic-ref --short HEAD)
if ($branch -ne 'main') { throw "You are on '$branch'. WITNESS uses a single branch: main." }

# Keep assistant files/names out of git WITHOUT touching any working file. Everything here lives in .git/ (never pushed).
$gitDir = Join-Path $root '.git'
New-Item -ItemType Directory -Force (Join-Path $gitDir 'info') | Out-Null
function Add-LineOnce($file, $line) {
  $have = if (Test-Path $file) { @(Get-Content $file) } else { @() }
  if ($have -notcontains $line) { Add-Content -Path $file -Value $line }
}
Add-LineOnce (Join-Path $gitDir 'info\exclude') "$($ai.ToUpper()).md"
Add-LineOnce (Join-Path $gitDir 'info\exclude') ".$ai/"
Add-LineOnce (Join-Path $gitDir 'info\attributes') '*.md filter=scrub'
Add-LineOnce (Join-Path $gitDir 'info\attributes') '*.ps1 filter=scrub'
$scrub = @'
$in = [Console]::OpenStandardInput(); $ms = New-Object IO.MemoryStream; $in.CopyTo($ms)
$t = [Text.Encoding]::UTF8.GetString($ms.ToArray())
$n = 'cl' + 'aude'
$t = [regex]::Replace($t, '(?i)' + $n + '\.md', 'AGENTS.md')
$t = [regex]::Replace($t, '(?i)\b' + $n + '\b', 'the AI assistant')
$o = [Console]::OpenStandardOutput(); $b = (New-Object Text.UTF8Encoding $false).GetBytes($t); $o.Write($b, 0, $b.Length); $o.Flush()
'@
[IO.File]::WriteAllText((Join-Path $gitDir 'scrub.ps1'), $scrub, [Text.UTF8Encoding]::new($false))
# Checkout side: put the original wording back, so pull/rebase never rewrites your local files with the scrubbed text.
$unscrub = @'
$in = [Console]::OpenStandardInput(); $ms = New-Object IO.MemoryStream; $in.CopyTo($ms)
$t = [Text.Encoding]::UTF8.GetString($ms.ToArray())
$t = [regex]::Replace($t, 'AGENTS\.md', ('CL' + 'AUDE') + '.md')
$o = [Console]::OpenStandardOutput(); $b = (New-Object Text.UTF8Encoding $false).GetBytes($t); $o.Write($b, 0, $b.Length); $o.Flush()
'@
[IO.File]::WriteAllText((Join-Path $gitDir 'unscrub.ps1'), $unscrub, [Text.UTF8Encoding]::new($false))
Invoke-Git config filter.scrub.clean 'powershell -NoProfile -ExecutionPolicy Bypass -File .git/scrub.ps1'
Invoke-Git config filter.scrub.smudge 'powershell -NoProfile -ExecutionPolicy Bypass -File .git/unscrub.ps1'   # required=true needs BOTH sides defined or every checkout/rebase fails
Invoke-Git config filter.scrub.required true

# 3. Stage only this role's paths, then refuse anything that must never be committed.
$existing = @($paths | Where-Object { Test-Path (Join-Path $root $_) })
Invoke-Git add -A -- @existing
$staged = @(& git.exe diff --cached --name-only)
$bad = @($staged | Where-Object { $_ -match '(^|/)\.env$' -or $_ -match '(^|/)\.venv/' -or $_ -match '(^|/)node_modules/' })
$leak = @(& git.exe diff --cached -U0 | Select-String -Pattern 'AIza[0-9A-Za-z_\-]{30,}|GEMINI_API_KEY[ \t]*=[ \t]*[^\s#]+')
# No AI-assistant files or names in the repo: assistant config files, and any staged text naming one.
$aiFiles = @($staged | Where-Object { $_ -match ("(?i)(^|/)($ai[^/]*|\.$ai)(/|$)") })
$aiText = @(& git.exe diff --cached -U0 | Select-String -Pattern $aiPat)
if (($bad.Count -gt 0) -or ($leak.Count -gt 0) -or ($aiFiles.Count -gt 0) -or ($aiText.Count -gt 0)) {
  & git.exe reset -q
  if ($bad.Count -gt 0) { throw "Refusing to commit: $($bad -join ', '). Add it to .gitignore." }
  if ($aiFiles.Count -gt 0) { throw "Refusing to commit assistant files: $($aiFiles -join ', '). Add them to .gitignore." }
  if ($aiText.Count -gt 0) { throw "Refusing to commit: staged text names an AI assistant or adds a co-author line: $($aiText[0].Line.Trim())" }
  throw "Refusing to commit: a Gemini API key appears in the staged changes. Remove it first."
}

# 4. Commit.
& git.exe diff --cached --quiet
if ($LASTEXITCODE -ne 0) {
  $msg = "[$tag] phase ${Phase}: $Message"
  if ($Trailer) { Invoke-Git commit -m $msg -m $Trailer } else { Invoke-Git commit -m $msg }
} else {
  Write-Host "Nothing new to commit; pushing existing commits."
}

# 5. Pull --rebase (only if main already exists on the remote), then push. Never force.
& git.exe ls-remote --exit-code --heads origin main *> $null
if ($LASTEXITCODE -eq 0) {
  Invoke-Git pull --rebase origin main
} elseif ($LASTEXITCODE -ne 2) {
  throw "Cannot reach origin (exit $LASTEXITCODE). Check network and GitHub login, then re-run."
}
Invoke-Git push -u origin main
Write-Host ""
Write-Host "Phase $Phase pushed:" -ForegroundColor Green
& git.exe log -1 --oneline

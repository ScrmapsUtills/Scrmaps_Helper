param([string]$Python)
$ErrorActionPreference = 'Stop'
. (Join-Path (Split-Path $PSScriptRoot -Parent) 'native_process.ps1')
if (-not $Python) { throw 'Pass -Python with a Python executable path.' }
$tests = 0
function Assert-True($Value, [string]$Message) {
    if (-not $Value) { throw $Message }
}

# Exactly the failure class in the uploaded setup.log: a candidate writes a
# traceback to stderr and exits nonzero while ErrorActionPreference is Stop.
$bad = Invoke-NativeProcess -FilePath $Python -Arguments @('-c','import sys; sys.stderr.write("Traceback: missing tkinter\n"); sys.exit(1)') -TimeoutSeconds 10
Assert-True ($bad.ExitCode -eq 1) 'A rejected probe must return exit code 1.'
Assert-True ($bad.Error.Contains('Traceback: missing tkinter')) 'The full stderr must be retained.'
$tests++
$good = Invoke-NativeProcess -FilePath $Python -Arguments @('-c','print("next candidate accepted")') -TimeoutSeconds 10
Assert-True ($good.ExitCode -eq 0 -and $good.Output.Contains('next candidate accepted')) 'Setup must continue to the next candidate.'
$tests++

$expected = @('', 'plain', 'path with spaces', 'C:\folder with spaces\', 'quote"inside', 'backslash\"quote', '한글 경로')
$arguments = @('-c','import sys,json; print(json.dumps(sys.argv[1:], ensure_ascii=False))') + $expected
$roundtrip = Invoke-NativeProcess -FilePath $Python -Arguments $arguments -TimeoutSeconds 10
Assert-True ($roundtrip.ExitCode -eq 0) ('Argument roundtrip failed: ' + $roundtrip.Error)
$actual = @($roundtrip.Output | ConvertFrom-Json)
Assert-True ($actual.Count -eq $expected.Count) 'Argument count changed.'
for ($i=0; $i -lt $expected.Count; $i++) {
    Assert-True ($actual[$i] -ceq $expected[$i]) ('Argument changed at index ' + $i)
}
$tests++

$verbose = Invoke-NativeProcess -FilePath $Python -Arguments @('-c','import sys; sys.stdout.write("x"*200000); sys.stderr.write("y"*200000)') -TimeoutSeconds 10
Assert-True ($verbose.ExitCode -eq 0 -and $verbose.Output.Length -eq 200000 -and $verbose.Error.Length -eq 200000) 'Concurrent stdout/stderr drain failed.'
$tests++

$missing = Invoke-NativeProcess -FilePath (Join-Path $PSScriptRoot 'missing-python.exe') -Arguments @('-c','pass') -TimeoutSeconds 10
Assert-True ($missing.ExitCode -eq -1 -and $missing.Error) 'A missing candidate must not terminate setup.'
$tests++

$failed = $false
try {
    Invoke-RequiredPython -Python $Python -Arguments @('-c','import sys; sys.stderr.write("complete install diagnostic\n"); sys.exit(9)') -Failure 'Expected failure'
} catch { $failed = $_.Exception.Message.Contains('Exit code: 9') }
Assert-True $failed 'Required steps must fail explicitly with an exit code.'
$tests++

foreach ($name in @('start.ps1','native_process.ps1')) {
    $tokens=$null; $parseErrors=$null
    [void][System.Management.Automation.Language.Parser]::ParseFile((Join-Path (Split-Path $PSScriptRoot -Parent) $name),[ref]$tokens,[ref]$parseErrors)
    Assert-True ($parseErrors.Count -eq 0) ('PowerShell parser errors: ' + $name)
    $tests++
}
Write-Host ('PASS: ' + $tests + ' setup regression checks')

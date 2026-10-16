[CmdletBinding()]
param(
    [ValidateSet('connect','login','status','port-forward')][string]$Action = 'connect',
    [string]$Profile = 'evidenceguard-prod15',
    [ValidateRange(1024,65535)][int]$LocalPort = 8795,
    [switch]$NoSystemProxy
)
$ErrorActionPreference = 'Stop'
# AWS CLI does not inherit Windows' proxy. Read the existing setting only;
# never alter the OS proxy, credentials, firewall, or certificate verification.
if (-not $NoSystemProxy -and -not $env:HTTP_PROXY -and -not $env:HTTPS_PROXY) {
    $settings = Get-ItemProperty 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Internet Settings' -ErrorAction SilentlyContinue
    if ($settings.ProxyEnable -eq 1 -and $settings.ProxyServer) {
        $proxyByScheme = @{}
        foreach ($entry in $settings.ProxyServer.Split(';')) {
            $pair = $entry.Split('=', 2)
            if ($pair.Count -eq 2) { $proxyByScheme[$pair[0].Trim()] = $pair[1].Trim() }
            elseif ($pair[0].Trim()) { $proxyByScheme['http'] = $pair[0].Trim(); $proxyByScheme['https'] = $pair[0].Trim() }
        }
        foreach ($scheme in @('http', 'https')) {
            $proxyAddress = $proxyByScheme[$scheme]
            if ($proxyAddress) {
                if ($proxyAddress -notmatch '^\w+://') { $proxyAddress = 'http://' + $proxyAddress }
                if ($proxyAddress -match '^https?://') { [Environment]::SetEnvironmentVariable($scheme.ToUpper() + '_PROXY', $proxyAddress, 'Process') }
            }
        }
        if (-not $env:NO_PROXY) { $env:NO_PROXY = '127.0.0.1,localhost,::1' }
    }
}
$env:AWS_PAGER = ''
$env:AWS_CLI_AUTO_PROMPT = 'off'
$awsCommand = Get-Command aws -ErrorAction SilentlyContinue
$awsPath = if ($awsCommand) { $awsCommand.Source } else { Join-Path $env:LOCALAPPDATA 'Programs\Amazon\AWSCLIV2\aws.exe' }
$pluginDir = Join-Path $env:LOCALAPPDATA 'Programs\Amazon\SessionManagerPlugin'
if (Test-Path -LiteralPath $pluginDir) { $env:PATH = $pluginDir + [IO.Path]::PathSeparator + $env:PATH }
if (-not (Test-Path -LiteralPath $awsPath)) { throw 'Install AWS CLI v2 first: https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html' }
$awsOptions = @('--profile',$Profile,'--region','ap-southeast-1','--no-cli-pager')
if ($Action -eq 'login') {
    & $awsPath @awsOptions login --remote
    exit $LASTEXITCODE
}
$identityJson = & $awsPath @awsOptions sts get-caller-identity --output json
if ($LASTEXITCODE -ne 0) { throw 'AWS identity check failed. See the network/authentication error above. If login expired, run: .\scripts\cloud_session.ps1 -Action login' }
$identity = $identityJson | ConvertFrom-Json
if ($identity.Account -ne '083151142234') { throw 'Wrong AWS account. No server operation was performed.' }
if ($Action -eq 'status') {
    & $awsPath @awsOptions ec2 describe-instances --instance-ids i-010907ed19e2cc23a --query 'Reservations[].Instances[].{Instance:InstanceId,State:State.Name,PublicIp:PublicIpAddress,PrivateIp:PrivateIpAddress}' --output table
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    & $awsPath @awsOptions ssm describe-instance-information --filters 'Key=InstanceIds,Values=i-010907ed19e2cc23a' --query 'InstanceInformationList[].{Instance:InstanceId,Status:PingStatus,OS:PlatformName,Version:PlatformVersion}' --output table
} elseif ($Action -eq 'port-forward') {
    $parameters = '{"portNumber":["8795"],"localPortNumber":["' + $LocalPort + '"]}'
    & $awsPath @awsOptions ssm start-session --target i-010907ed19e2cc23a --document-name AWS-StartPortForwardingSession --parameters $parameters
} else {
    & $awsPath @awsOptions ssm start-session --target i-010907ed19e2cc23a
}
exit $LASTEXITCODE

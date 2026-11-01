Only one place in the whole app returns 403 — that setup filter — so it is the IP comparison. The capture came back empty because the job hadn't connected yet in 400ms.

Hold a connection open so the query can see it:

```powershell
$p = 'D:\HSBCArchive\app\appsettings.UAT.json'
$j = Get-Content -LiteralPath $p -Raw | ConvertFrom-Json
$ips = @('127.0.0.1','::1','136.25.66.82','fe80::5ca4:e723:1b6c:9808%6') +
       (Get-NetIPAddress | Select-Object -ExpandProperty IPAddress)
$j.Archive.Deployment.SetupAllowedIPs = [string[]]($ips | Sort-Object -Unique)
$j | ConvertTo-Json -Depth 24 | Set-Content -LiteralPath $p -Encoding UTF8
$j.Archive.Deployment.SetupAllowedIPs
Restart-Service HSBCArchive
Start-Sleep 25
(Invoke-WebRequest https://bdw25135475:9443/ -UseBasicParsing -ErrorAction SilentlyContinue).StatusCode
```

That will show the address the app sees. But rather than go round again, just allow every address this server owns — remote machines stay blocked either way, and the window gets closed after the wizard:

```powershell
$r = Invoke-WebRequest https://bdw25135475:9443/ -UseBasicParsing
($r.Content | Select-String -Pattern '(?s).{200}DatabaseProvider.{400}' -AllMatches).Matches.Value
```

Want `200`. If an IPv6 address shows up in that printed list that wasn't in your three, that was the culprit.

This widens the allowlist to the server itself only — no other machine can reach the wizard. Still close it properly once setup is done, and send me the `RemoteAddress` from the first command if you ran it, so we know what it actually was.

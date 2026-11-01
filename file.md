The log is clean — no antiforgery failure, no host rejection, no exception. The request arrives and something returns 400 without logging a thing. Combined with the blank page earlier, I think the browser is the problem: that server only has **Internet Explorer**, and Orchard's setup form won't post correctly from IE11.

Test it from your own laptop with a modern browser. Add your laptop's IP to the allowlist first:

On **your laptop**, get its address:

```powershell
ipconfig | Select-String IPv4
```

Then on the **server**:

```powershell
$p = 'D:\HSBCArchive\app\appsettings.UAT.json'
$j = Get-Content -LiteralPath $p -Raw | ConvertFrom-Json
$j.Archive.Deployment.SetupAllowedIPs = [string[]]($j.Archive.Deployment.SetupAllowedIPs + '<your laptop IPv4>')
$j | ConvertTo-Json -Depth 24 | Set-Content -LiteralPath $p -Encoding UTF8
$j.Archive.Deployment.SetupAllowedIPs
Restart-Service HSBCArchive
```

Then from your laptop open **https://bdw25135475:9443** in Edge or Chrome. You'll get a certificate warning — click through it (Advanced → Proceed), since the self-signed certificate isn't trusted there yet.

If the wizard completes from your laptop, that confirms IE was the problem, and it's worth noting in the handover: the archive needs a modern browser, so the server console is not a usable client.

If your laptop can't reach the server at all, check from the laptop:

```powershell
Test-NetConnection -ComputerName bdw25135475 -Port 9443
```

Before you do all that — which browser were you using on the server when you clicked Finish? If it was IE, this is almost certainly it.

The app is fine then — `Running` and `/health` returning 200.

So it's the browser side. Try **https://bdw25135475:9443** from your laptop again (the one that worked before), and tell me the exact message.

Two things that commonly break at this point:

**The allowlist** — confirm your laptop's IP is still there:

```powershell
(Get-Content D:\HSBCArchive\app\appsettings.UAT.json -Raw | ConvertFrom-Json).Archive.Deployment.SetupAllowedIPs
```

It should still include your laptop's IPv4 — the edits only touched two fields, but worth confirming. Note that a missing entry gives **403**, not "page not found".

**Which URL you used** — it must be `https://` and include `:9443`. Without the port the browser tries 443, which is Tomcat's, and without `https` it tries plain HTTP on a TLS-only port; both look like "can't find the page".

If the laptop genuinely can't connect, check from the laptop:

```powershell
Test-NetConnection -ComputerName bdw25135475 -Port 9443
```

`TcpTestSucceeded : False` would mean the firewall rule is missing — but nothing we changed should have removed it.

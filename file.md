Then the network is fine and it's the HTTP layer. Get the real status from the laptop, bypassing the browser:

```powershell
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
[Net.ServicePointManager]::ServerCertificateValidationCallback = { $true }
$r = Invoke-WebRequest https://bdw25135475:9443/ -UseBasicParsing -ErrorAction SilentlyContinue
$r.StatusCode
$r.Content.Length
```

That tells us which problem it is:

- **200 with content** → the server is serving fine and the browser is at fault; hard-refresh with Ctrl+Shift+R, or try a private window — it may be caching the earlier failure.
- **403** → allowlist mismatch despite the entry (different IP than you think).
- **400** → `AllowedHosts`. Make sure you're browsing `https://bdw25135475:9443` and not the FQDN `bdw25135475.hbap.adroot.hsbc:9443`, since only the short name is allowed right now.
- **An error, no status** → TLS. The self-signed certificate isn't trusted on the laptop; in the browser click Advanced → Proceed.

Also paste me the exact wording the browser shows — "no web page found" is phrased differently by Edge, Chrome and IE, and the wording identifies which layer is failing.

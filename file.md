There it is — `tenants.json`. Orchard 3.x keeps tenant state in that file, not in a `Sites` folder, so deleting `Sites` removed nothing. It still records the Default tenant as already set up, which is why root returns 404 instead of the wizard.

```powershell
Stop-Service HSBCArchive
Get-Content D:\HSBCArchiveData\Runtime\Orchard\tenants.json
Remove-Item D:\HSBCArchiveData\Runtime\Orchard\* -Recurse -Force
Start-Service HSBCArchive
Start-Sleep 25
(Invoke-WebRequest https://bdw25135475:9443/ -UseBasicParsing -ErrorAction SilentlyContinue).StatusCode
```

The `Get-Content` just shows you what it said before deleting. Only that folder goes — the data-protection keys live in `D:\HSBCArchiveData\Runtime\Keys`, which is untouched.

Expect `200`, then the wizard at **https://bdw25135475:9443** from your laptop.

Your AD settings now read `45517160` with domain `hbap.adroot.hsbc`, which matches the account that returned `True` — so after the wizard, log in with that ID and your Windows password.

Worth noting for the handover: a clean reinstall needs *both* the database dropped and `Runtime\Orchard\tenants.json` removed. Doing only one leaves the archive in this half-state.

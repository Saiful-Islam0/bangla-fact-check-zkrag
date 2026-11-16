Found it. Two different situations:

## Issue 2 is expected — not a bug

The chip is hidden because **Windows Authentication isn't enabled in IIS yet**. Right now `/archive/whoami` returns 401, the script retries, gets 204, and stays hidden — exactly as designed. You can confirm by opening `https://<host>:9443/archive/whoami` directly.

To turn it on: **IIS Manager → your site → Authentication → enable Windows Authentication**, keep **Anonymous enabled and as the default**, then recycle the pool.

I earlier said wait for the SPN and Group Policy. Worth trying now anyway: your hostname is a short name with no dots, which Windows usually classifies as Local Intranet automatically, so it may negotiate silently without the GPO push. If you get a credential prompt instead, turn it back off and wait for the AD team.

## Issue 1 is real — wrong media root, almost certainly

Images are stored at **`<MediaRoot>\Default`** — the code appends the tenant name. Two ways this breaks:

- You entered a **different** media root than the service used → new empty folder
- You entered `...\Media\Default` when the old value was `...\Media` → app now looks in `...\Media\Default\Default`

Either way the installer *creates* the folder and sets permissions without complaint, so there's no error — just no images. Same shape as the database name.

**Compare what the site uses now against what the service used:**

```powershell
# What IIS is using now
Import-Module WebAdministration
(Get-WebConfiguration -PSPath 'MACHINE/WEBROOT/APPHOST' `
  -Filter 'system.applicationHost/applicationPools/add[@name="HSBCArchive"]/environmentVariables').Collection |
  Where-Object { $_.name -like '*StorageRoot*' -or $_.name -like '*DataRoot*' } |
  Format-Table name, value -AutoSize

# What the old service used (still in the registry — it's disabled, not removed)
(Get-ItemProperty 'HKLM:\SYSTEM\CurrentControlSet\Services\HSBCArchive').Environment |
  Where-Object { $_ -like '*StorageRoot*' -or $_ -like '*DataRoot*' }
```

**Then find where your images actually are:**

```powershell
Get-ChildItem D:\ -Recurse -Directory -Filter 'Default' -ErrorAction SilentlyContinue |
  ForEach-Object {
    $n = (Get-ChildItem $_.FullName -Recurse -File -ErrorAction SilentlyContinue | Measure-Object).Count
    if ($n -gt 0) { "{0}  ({1} files)" -f $_.FullName, $n }
  }
```

The folder with your images is `<the right MediaRoot>\Default`. So if that prints `D:\HSBCArchiveData\Media\Default`, your media root is `D:\HSBCArchiveData\Media`.

**To fix, just correct the pool variable — no reinstall:**

```powershell
Import-Module WebAdministration
$pool = "IIS:\AppPools\HSBCArchive"
$env  = (Get-ItemProperty $pool).environmentVariables
# then set the StorageRoot entry to the correct parent path, and:
Restart-WebAppPool -Name HSBCArchive
```

Easiest is IIS Manager → Application Pools → HSBCArchive → Advanced Settings → Environment Variables → fix the `...Media__StorageRoot` value → OK → recycle.

**One thing to check after fixing:** the installer runs `icacls /inheritance:r`, which *strips* inherited permissions and grants only the pool identity, Administrators and SYSTEM. It only did that to the path you gave it. If your real media folder wasn't that path, it still has the old service's permissions, so grant the pool identity access:

```powershell
icacls "<real MediaRoot>\Default" /grant "IIS AppPool\HSBCArchive:(OI)(CI)M"
```

If images still don't appear after that, check the Windows Event Log for **event 2404**, which the app logs when a preview file is missing — that distinguishes "wrong folder" from "file genuinely absent".

ACLs are right now — `Drop` shows `NT AUTHORITY\NETWORK SERVICE:(OI)(CI)(M)`, and Runtime/Media were re-secured (10 and 89 files). But the service won't stay up.

The Service Control Manager logs start failures to the **System** log, not Application — that's a different place from everywhere we've looked:

```powershell
Get-WinEvent -FilterHashtable @{LogName='System'; ProviderName='Service Control Manager'} -MaxEvents 15 |
  Where-Object { $_.Message -like '*HSBCArchive*' } |
  Format-List TimeCreated, Id, Message
```

And in parallel, the app's own startup error:

```powershell
foreach ($e in (Get-ItemProperty 'HKLM:\SYSTEM\CurrentControlSet\Services\HSBCArchive').Environment) {
    $k, $v = $e -split '=', 2
    Set-Item -Path "Env:$k" -Value $v
}
cd D:\HSBCArchive\app
.\HSBC.Archive.Web.exe
```

Send me the first error from either.

If the foreground run starts cleanly — which it may, since you have Full Control on those folders — then something is still blocked for `NETWORK SERVICE` specifically, and the next check is the parent folder, which my script never touched:

```powershell
icacls D:\HSBCArchiveData
```

`NETWORK SERVICE` needs at least traverse/read there to reach the three sub-folders. It previously had that through `BUILTIN\Users` inherited from `D:\`; if that's still intact it's not the cause, but it's the obvious gap given I locked the children down and left the parent alone.

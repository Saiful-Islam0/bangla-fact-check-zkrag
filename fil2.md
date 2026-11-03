That's the decisive clue: it works when **you** run it, and fails when the **service** runs it. Same code, same files — different identity. So this is permissions on something `NT AUTHORITY\NETWORK SERVICE` can't touch.

First, get the error properly. `Get-EventLog` has never found anything all session; `Get-WinEvent` uses a different API and usually does:

```powershell
Get-WinEvent -FilterHashtable @{LogName='Application'; ProviderName='HSBCArchiveUAT'} -MaxEvents 20 -ErrorAction SilentlyContinue |
  Format-List TimeCreated, Id, Message
```

Then check what the service account can actually reach:

```powershell
icacls D:\HSBCArchiveData\Drop
Get-ChildItem D:\HSBCArchiveData\Drop -File | ForEach-Object { icacls $_.FullName }
icacls D:\HSBCArchiveData\Media
icacls D:\HSBCArchiveData\Runtime
```

Every one of those should list `NT AUTHORITY\NETWORK SERVICE:(M)` or `(OI)(CI)(M)`. The photo matters as much as the folder — ingest needs to **read it, create `_done`, and move it**, so the file itself needs delete rights, not just read. A file copied in before the ACL was set, or copied by a tool that preserves source permissions, can easily lack them.

To confirm the diagnosis in one step, temporarily run the service with full rights:

```powershell
sc.exe config HSBCArchive obj= LocalSystem
Restart-Service HSBCArchive
```

Try the ingest. **If it works, it's definitely permissions** — and then put it straight back, because LocalSystem is far more privileged than this service should ever be:

```powershell
sc.exe config HSBCArchive 'obj=' 'NT AUTHORITY\NETWORK SERVICE'
Restart-Service HSBCArchive
```

Don't leave it on LocalSystem even overnight.

Send me the `Get-WinEvent` output and the `icacls` results. One thing I'd like to know either way: when the service was running it, did the **thumbnails still appear**? If they did, reading works and it's the move or the media write that's failing — which points at different folders.

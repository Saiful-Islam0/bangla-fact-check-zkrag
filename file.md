Get-Service | Where-Object { $_.Name -like 'MSSQL*' } | Select-Object Name, Status
Get-NetTCPConnection -State Listen | Where-Object { $_.LocalPort -in 1433,1434 } | Select-Object LocalAddress, LocalPort
Get-NetFirewallRule -Enabled True -Direction Inbound | Where-Object DisplayName -like '*SQL*' | Select-Object DisplayName

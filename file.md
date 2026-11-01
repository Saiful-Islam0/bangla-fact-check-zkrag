$pw = Read-Host 'SQL password' -AsSecureString
$cs = New-Object System.Data.SqlClient.SqlConnectionStringBuilder
$cs['Data Source'] = 'BDW25135476\UBDRMSS01'
$cs['Initial Catalog'] = 'BDArchive'
$cs['User ID'] = 'bdarchive'
$cs['Password'] = [Runtime.InteropServices.Marshal]::PtrToStringUni([Runtime.InteropServices.Marshal]::SecureStringToGlobalAllocUnicode($pw))
$cs['Encrypt'] = $true
$cs['TrustServerCertificate'] = $true
$conn = New-Object System.Data.SqlClient.SqlConnection $cs.ConnectionString
$conn.Open(); $conn.ServerVersion; $conn.Close()

$cert = New-SelfSignedCertificate -Subject 'CN=HSBCArchiveUAT' `
  -DnsName 'bdw25135475','bdw25135475.hbap.adroot.hsbc' `
  -CertStoreLocation Cert:\LocalMachine\My `
  -FriendlyName 'HSBC Archive UAT' -NotAfter (Get-Date).AddYears(2)
Export-Certificate -Cert $cert -FilePath D:\HSBCArchive\archive-uat.cer | Out-Null
Import-Certificate -FilePath D:\HSBCArchive\archive-uat.cer -CertStoreLocation Cert:\LocalMachine\Root | Out-Null
$cert.Thumbprint

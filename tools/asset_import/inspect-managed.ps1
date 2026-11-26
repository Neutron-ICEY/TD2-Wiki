param(
    [string]$InputFile,
    [long]$Offset = 0,
    [int]$Length,
    [switch]$Base64Stdin,
    [string]$Selector = '',
    [Parameter(Mandatory=$true)][string]$OutputFile
)
$ErrorActionPreference = 'Stop'
# PowerShell's installed metadata library; no SDK installation or application load.
Add-Type -Path (Join-Path $PSScriptRoot 'ManagedInspector.cs') -ReferencedAssemblies @(
    'System.Reflection.Metadata', 'System.Collections.Immutable', 'System.Reflection.Emit.ILGeneration', 'System.Reflection.Primitives',
    'System.Runtime', 'System.Collections', 'System.Linq', 'System.Text.RegularExpressions'
)
if ($Base64Stdin) {
    $bytes = [Convert]::FromBase64String([Console]::In.ReadToEnd())
    $result = [TD2ManagedInspector]::InspectData($bytes, $Selector)
} else {
    $result = [TD2ManagedInspector]::Inspect($InputFile, $Offset, $Length, $Selector)
}
$result | ConvertTo-Json -Depth 100 | Set-Content -LiteralPath $OutputFile -Encoding utf8NoBOM

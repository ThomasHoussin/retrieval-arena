param([Parameter(Mandatory=$true)][string]$DocumentPath)
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)
$wordApp = $null
$wordDocument = $null
$oldUpdateLinks = $null
$saveChanges = 0
try {
    $wordApp = New-Object -ComObject Word.Application
    $wordApp.Visible = $false
    $wordApp.DisplayAlerts = 0
    $wordApp.AutomationSecurity = 3
    $oldUpdateLinks = $wordApp.Options.UpdateLinksAtOpen
    $wordApp.Options.UpdateLinksAtOpen = $false
    # ConfirmConversions=false, ReadOnly=true, AddToRecentFiles=false.
    $confirmConversions = $false
    $readOnly = $true
    $addToRecentFiles = $false
    $wordDocument = $wordApp.Documents.Open([ref]$DocumentPath, [ref]$confirmConversions, [ref]$readOnly, [ref]$addToRecentFiles)
    $plainText = $wordDocument.Content.Text
    [Console]::Write([Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($plainText)))
} finally {
    if ($null -ne $wordDocument) {
        $wordDocument.Close([ref]$saveChanges)
        [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($wordDocument)
    }
    if ($null -ne $wordApp) {
        if ($null -ne $oldUpdateLinks) { $wordApp.Options.UpdateLinksAtOpen = $oldUpdateLinks }
        $wordApp.Quit([ref]$saveChanges)
        [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($wordApp)
    }
}

#!/usr/bin/env pwsh
# One-shot scrape used by the scheduled GitHub Actions workflow.
# Pulls Klix + crna-hronika RSS, resolves location, keeps only Bosnia news,
# de-duplicates across sources, and posts signed webhooks to the backend.
# Configuration comes from environment variables:
#   WEBHOOK_SECRET       (required) - HMAC signing secret, shared with the backend
#   WEBHOOK_TARGET_URL   (optional) - backend webhook endpoint
#   SCRAPE_LIMIT         (optional) - max items per source (default 40)

$ErrorActionPreference = "Stop"

$Secret = $env:WEBHOOK_SECRET
if ([string]::IsNullOrWhiteSpace($Secret)) { throw "WEBHOOK_SECRET environment variable is not set" }
$API = if ($env:WEBHOOK_TARGET_URL) { $env:WEBHOOK_TARGET_URL } else { "https://bhsignal-api-production.up.railway.app/api/v1/webhooks/news" }
$Limit = if ($env:SCRAPE_LIMIT) { [int]$env:SCRAPE_LIMIT } else { 40 }
$UA = "GeoNewsScraperBot/0.1 (+https://example.org/geonews)"
$catalogPath = Join-Path $PSScriptRoot "..\app\data\location_catalog.json"

$catalog = Get-Content $catalogPath -Raw -Encoding UTF8 | ConvertFrom-Json

function Normalize([string]$text) {
  if ([string]::IsNullOrEmpty($text)) { return "" }
  $formD = $text.Normalize([Text.NormalizationForm]::FormKD)
  $sb = New-Object System.Text.StringBuilder
  foreach ($ch in $formD.ToCharArray()) {
    $cat = [Globalization.CharUnicodeInfo]::GetUnicodeCategory($ch)
    if ($cat -eq [Globalization.UnicodeCategory]::NonSpacingMark) { continue }
    if ([int][char]$ch -ge 128) { continue }
    [void]$sb.Append($ch)
  }
  $s = $sb.ToString().ToLowerInvariant()
  return ([Regex]::Replace($s, "\s+", " ")).Trim()
}

function ContainsAlias([string]$text, [string]$alias) {
  if ($alias.Length -lt 2) { return $false }
  if ($alias.Length -ge 4) {
    $pattern = "(^|[^a-z0-9])" + [Regex]::Escape($alias) + "[a-z]*([^a-z0-9]|$)"
  } else {
    $pattern = "(^|[^a-z0-9])" + [Regex]::Escape($alias) + "([^a-z0-9]|$)"
  }
  return [Regex]::IsMatch($text, $pattern)
}

function ResolveLocation([string]$title, [string]$summary, [string]$category) {
  $nt = Normalize $title
  $ns = Normalize $summary
  $nc = Normalize $category
  $bestLoc = $null; $bestAlias = $null; $bestScore = 0.0
  foreach ($loc in $catalog) {
    foreach ($alias in $loc.aliases) {
      $an = Normalize $alias
      $th = ContainsAlias $nt $an
      $sh = ContainsAlias $ns $an
      $ch = ContainsAlias $nc $an
      if (-not ($th -or $sh -or $ch)) { continue }
      $score = 0.0
      if ($th) { $score += 0.65 }
      if ($sh) { $score += 0.25 }
      if ($ch) { $score += 0.10 }
      if ($score -gt $bestScore) { $bestScore = $score; $bestLoc = $loc; $bestAlias = $alias }
    }
  }
  if ($null -ne $bestLoc) {
    $conf = [Math]::Min(0.98, 0.30 + $bestScore)
    return [pscustomobject]@{
      locationTagRaw = $bestAlias; locationName = $bestLoc.name
      latitude = [double]$bestLoc.latitude; longitude = [double]$bestLoc.longitude
      locationConfidence = [Math]::Round($conf, 2); precision = $bestLoc.precision
      isBosnia = [bool]$bestLoc.bosnia
    }
  }
  $fallbacks = @{ "bih" = "Bosnia and Herzegovina"; "regija" = "Balkans"; "svijet" = "World" }
  if ($fallbacks.ContainsKey($nc)) {
    $fb = $catalog | Where-Object { $_.name -eq $fallbacks[$nc] } | Select-Object -First 1
    if ($fb) {
      return [pscustomobject]@{
        locationTagRaw = $category; locationName = $fb.name
        latitude = [double]$fb.latitude; longitude = [double]$fb.longitude
        locationConfidence = 0.42; precision = $fb.precision
        isBosnia = [bool]$fb.bosnia
      }
    }
  }
  return [pscustomobject]@{
    locationTagRaw = $null; locationName = $null; latitude = $null; longitude = $null
    locationConfidence = 0.0; precision = "unknown"; isBosnia = $false
  }
}

function StripHtml([string]$s) {
  if (-not $s) { return "" }
  $t = [Regex]::Replace($s, "<[^>]+>", " ")
  $t = [Regex]::Replace($t, "\s+", " ").Trim()
  return [System.Net.WebUtility]::HtmlDecode($t)
}

function NormalizeCategory([string]$path) {
  $p = $path.ToLowerInvariant()
  if ($p -match "crna-hronika") { return "CRNA HRONIKA" }
  if ($p -match "(^|/)(sport|nogomet|kosarka|tenis|odbojka|rukomet|formula)") { return "SPORT" }
  if ($p -match "kultura") { return "KULTURA" }
  if ($p -match "(biznis|ekonomija)") { return "BIZNIS" }
  if ($p -match "(^|/)auto") { return "AUTO" }
  if ($p -match "(lifestyle|modailjepota|magazin|show|zdravlje)") { return "LIFESTYLE" }
  if ($p -match "(scitech|nauka|tehnologija|tech)") { return "TECH" }
  return "VIJESTI"
}

function CrnaHronikaCategory([string]$title, [string]$summary) {
  $t = Normalize "$title $summary"
  if ($t -match "(uhapsen|uhicen|ubijen|ubistvo|ubili|droga|narkotik|policij|nesrec|povrijed|krad|napad|oruzj|pretres|razbojnis|poginu|saobracajn|nasilj|prevar|ukral)") {
    return "CRNA HRONIKA"
  }
  return "VIJESTI"
}

function Get-ArticleId([string]$link) {
  $m = [Regex]::Match($link, "/(\d{6,})/?$")
  if ($m.Success) { return $m.Groups[1].Value }
  $sha = [System.Security.Cryptography.SHA256]::Create()
  $h = $sha.ComputeHash([System.Text.Encoding]::UTF8.GetBytes($link))
  return (($h | ForEach-Object { $_.ToString("x2") }) -join "").Substring(0, 20)
}

$STOPWORDS = @(
  'u', 'i', 'na', 'je', 'su', 'se', 'za', 'od', 'do', 'o', 'a', 'da', 'ne', 'li', 's', 'sa',
  'ka', 'ko', 'te', 'ali', 'pa', 'ili', 'nije', 'bi', 'po', 'uz', 'iz', 'kao', 'sto', 'the',
  'of', 'in', 'to', 'and', 'jos', 'vec', 'si', 'ce', 'sve', 'koji', 'koja', 'koje', 'nakon'
)
$SUFFIXES = @(
  'ovima', 'evima', 'anje', 'enje', 'ima', 'ama', 'oga', 'ega', 'iju',
  'eo', 'ao', 'la', 'le', 'li', 'lo', 'og', 'eg', 'om', 'em', 'im', 'ih', 'ju',
  'a', 'e', 'i', 'o', 'u'
)
function Stem([string]$w) {
  foreach ($suf in $SUFFIXES) {
    if (($w.Length - $suf.Length) -ge 3 -and $w.EndsWith($suf)) {
      return $w.Substring(0, $w.Length - $suf.Length)
    }
  }
  return $w
}
function TitleTokens([string]$title) {
  $norm = Normalize $title
  $parts = [Regex]::Split($norm, "[^a-z0-9]+") | Where-Object { $_ }
  $set = New-Object 'System.Collections.Generic.HashSet[string]'
  foreach ($p in $parts) {
    if ($STOPWORDS -contains $p) { continue }
    if ($p.Length -lt 3 -and -not ($p -match '^\d+$')) { continue }
    $stem = if ($p -match '^\d+$') { $p } else { Stem $p }
    [void]$set.Add($stem)
  }
  return , $set
}
function IsDuplicateHeadline($tokens) {
  if ($tokens.Count -eq 0) { return $false }
  foreach ($seen in $script:seenTokenSets) {
    if ($seen.Count -eq 0) { continue }
    $inter = 0
    foreach ($t in $tokens) { if ($seen.Contains($t)) { $inter++ } }
    $union = $seen.Count + $tokens.Count - $inter
    if ($union -gt 0 -and ($inter / $union) -ge 0.4) { return $true }
  }
  return $false
}

$hmac = New-Object System.Security.Cryptography.HMACSHA256
$hmac.Key = [System.Text.Encoding]::UTF8.GetBytes($Secret)

$script:seenTokenSets = New-Object System.Collections.ArrayList
$script:delivered = 0
$script:dup = 0
$script:failed = 0
$script:skippedNonBih = 0
$script:skippedDup = 0
$script:bihTotal = 0
$script:abort = $false

function Preload-Existing() {
  try {
    $wc = New-Object System.Net.WebClient
    $json = [System.Text.Encoding]::UTF8.GetString($wc.DownloadData("$($API -replace '/webhooks/news$','')/news?limit=500"))
    $existing = ($json | ConvertFrom-Json).items
    foreach ($it in $existing) { [void]$script:seenTokenSets.Add((TitleTokens $it.title)) }
    Write-Host "Preloaded $($existing.Count) existing headlines for dedup."
  } catch {
    Write-Host "Preload skipped: $($_.Exception.Message)"
  }
}

function Process-Feed([string]$rssUrl, [string]$source) {
  Write-Host ""
  Write-Host "---- $source ($rssUrl) ----"
  $wc = New-Object System.Net.WebClient
  $wc.Headers.Add("User-Agent", $UA)
  try {
    $bytes = $wc.DownloadData($rssUrl)
  } catch {
    Write-Host "  fetch failed: $($_.Exception.Message)"
    return
  }
  $xmlText = [System.Text.Encoding]::UTF8.GetString($bytes)
  [xml]$xml = $xmlText
  $nsm = New-Object System.Xml.XmlNamespaceManager($xml.NameTable)
  $nsm.AddNamespace("media", "http://search.yahoo.com/mrss/")
  $nsm.AddNamespace("dc", "http://purl.org/dc/elements/1.1/")

  $items = @($xml.rss.channel.item)
  if ($items.Count -gt $Limit) { $items = $items[0..($Limit - 1)] }

  foreach ($item in $items) {
    if ($script:abort) { return }
    $link = "$($item.link)"
    $title = StripHtml ("$($item.title)")
    if (-not $link -or -not $title) { continue }

    $artId = Get-ArticleId $link

    $descNode = $item.SelectSingleNode("description")
    $summary = if ($descNode) { StripHtml ($descNode.InnerText) } else { "" }

    try { $pub = [DateTimeOffset]::Parse($item.pubDate).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ") }
    catch { $pub = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ") }

    $uri = [Uri]$link
    if ($source -eq "klix") {
      $segs = $uri.AbsolutePath.Trim("/").Split("/")
      $subsection = if ($segs.Length -ge 2) { $segs[1] } elseif ($segs.Length -ge 1) { $segs[0] } else { "vijesti" }
      $category = NormalizeCategory $uri.AbsolutePath
    } else {
      $subsection = ""
      $category = CrnaHronikaCategory $title $summary
    }

    $authorNode = $item.SelectSingleNode("dc:creator", $nsm)
    $author = if ($authorNode) { $authorNode.InnerText } else { $null }

    $mediaNode = $item.SelectSingleNode("media:content", $nsm)
    $image = if ($mediaNode) { $mediaNode.GetAttribute("url") } else { $null }
    if (-not $image) {
      $encNode = $item.SelectSingleNode("enclosure")
      if ($encNode) { $image = $encNode.GetAttribute("url") }
    }

    $loc = ResolveLocation $title $summary $subsection

    if (-not $loc.isBosnia) {
      $script:skippedNonBih++
      continue
    }
    $script:bihTotal++

    $tokens = TitleTokens $title
    if (IsDuplicateHeadline $tokens) {
      $script:skippedDup++
      Write-Host "DEDUP ($source) $title"
      continue
    }
    [void]$script:seenTokenSets.Add($tokens)

    $data = [ordered]@{
      source = $source; sourceArticleId = $artId; title = $title; summary = $summary; url = $link
      publishedAt = $pub; category = $category; author = $author; imageUrl = $image
      locationTagRaw = $loc.locationTagRaw; locationName = $loc.locationName
      latitude = $loc.latitude; longitude = $loc.longitude
      locationConfidence = $loc.locationConfidence; precision = $loc.precision; updatedAt = $pub
    }
    $envelope = [ordered]@{
      eventType = "news.created"
      occurredAt = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")
      source = "geonews-scraper"
      data = $data
    }

    $json = $envelope | ConvertTo-Json -Depth 6 -Compress
    $bodyBytes = [System.Text.Encoding]::UTF8.GetBytes($json)
    $sig = "sha256=" + (($hmac.ComputeHash($bodyBytes) | ForEach-Object { $_.ToString("x2") }) -join "")
    $eventId = "ci-scrape-$source-$artId"

    $attempt = 0
    while ($true) {
      $attempt++
      try {
        $r = Invoke-WebRequest -Uri $API -Method Post -Body $bodyBytes `
          -Headers @{ "X-Event-Id" = $eventId; "X-Signature-256" = $sig } `
          -ContentType "application/json" -UseBasicParsing -TimeoutSec 25
        if ($r.StatusCode -eq 202) { $script:delivered++; Write-Host "OK   [$category] $($loc.locationName) | $title" }
        elseif ($r.StatusCode -eq 200) { $script:dup++; Write-Host "DUP  $title" }
        break
      } catch {
        $code = $null
        if ($_.Exception.Response) { $code = [int]$_.Exception.Response.StatusCode }
        if ($code -eq 403) {
          Write-Host "FAIL [403] webhook secret rejected"
          $script:abort = $true
          return
        }
        if (($code -ge 500 -or $null -eq $code) -and $attempt -lt 4) {
          Write-Host "  retry $attempt after transient error ($code)..."
          Start-Sleep -Seconds 5
          continue
        }
        $script:failed++
        Write-Host "FAIL [$code] $title"
        break
      }
    }
  }
}

Preload-Existing
Process-Feed "https://www.klix.ba/rss" "klix"
Process-Feed "https://crna-hronika.info/feed/" "crna-hronika"

Write-Host ""
Write-Host "==== SUMMARY ===="
Write-Host "BiH articles found across sources : $($script:bihTotal)"
Write-Host "delivered=$($script:delivered)  duplicate=$($script:dup)  failed=$($script:failed)"
Write-Host "skipped non-BiH=$($script:skippedNonBih)  skipped cross-source dup=$($script:skippedDup)"
if ($script:abort) { exit 1 }

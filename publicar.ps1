# Crea el repositorio "geoparquemet" en GitHub, sube la app y activa GitHub Pages desde /docs.
# Ejecutar UNA vez desde esta carpeta:  powershell -ExecutionPolicy Bypass -File .\publicar.ps1
# Usa la credencial de GitHub que ya guarda Git en este PC (no la muestra ni la guarda en ningún archivo).
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
$usuario = 'cvenegas-sernageomin'
$repo = 'geoparquemet'

$cred = "protocol=https`nhost=github.com`n`n" | git credential fill
$token = (($cred | Where-Object { $_ -like 'password=*' }) -replace '^password=', '')
if (-not $token) { throw 'No se encontró una credencial de GitHub guardada en Git.' }
$h = @{ Authorization = "token $token"; Accept = 'application/vnd.github+json'; 'User-Agent' = 'publicar-geoparquemet' }

try {
  Invoke-RestMethod -Method Get -Uri "https://api.github.com/repos/$usuario/$repo" -Headers $h | Out-Null
  Write-Host "El repositorio $repo ya existe."
} catch {
  $cuerpo = @{ name = $repo; description = 'GeoParquemet: geotour con GPS de la Geo-Ruta 1 Pio Nono - Tupahue (Parque Metropolitano de Santiago)'; homepage = "https://$usuario.github.io/$repo/"; has_wiki = $false } | ConvertTo-Json
  Invoke-RestMethod -Method Post -Uri 'https://api.github.com/user/repos' -Headers $h -Body $cuerpo -ContentType 'application/json' | Out-Null
  Write-Host "Repositorio $repo creado."
}

if (-not (git remote | Select-String -Quiet '^origin$')) { git remote add origin "https://github.com/$usuario/$repo.git" }
git push -u origin main

try {
  $pages = @{ source = @{ branch = 'main'; path = '/docs' } } | ConvertTo-Json
  Invoke-RestMethod -Method Post -Uri "https://api.github.com/repos/$usuario/$repo/pages" -Headers $h -Body $pages -ContentType 'application/json' | Out-Null
  Write-Host 'GitHub Pages activado.'
} catch { Write-Host 'GitHub Pages ya estaba activado (o se activará en unos segundos).' }

Write-Host ''
Write-Host "Listo. En 1-2 minutos estará en: https://$usuario.github.io/$repo/"

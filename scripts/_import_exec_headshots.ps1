Add-Type -AssemblyName System.Drawing

$proj = 'C:\Users\modha\Desktop\ASME-web-backend-'
$dest = Join-Path $proj 'static\images\executive'
New-Item -ItemType Directory -Force -Path $dest | Out-Null

$src = 'C:\Users\modha\Desktop\ASME exec'
$map = @(
  @{ from = 'Conover, Paul\IMG_9965.jpg';                 to = 'paul_conover.jpg'   },
  @{ from = 'Dexter, Corbin\Media.jpg';                   to = 'corbin_dexter.jpg'  },
  @{ from = 'Etnyre, Jet\image.jpg';                      to = 'jet_etnyre.jpg'     },
  @{ from = 'Fish, Dawson\ProfessionalHeadshot.jpg';      to = 'dawson_fish.jpg'    },
  @{ from = 'Fish, Nathan\IMG_5375.jpg';                  to = 'nathan_fish.jpg'    },
  @{ from = 'Hefel, Preston\image.png';                   to = 'preston_hefel.jpg'  },
  @{ from = 'Maire, Ryan\IMG_6167.JPG';                   to = 'ryan_maire.jpg'     },
  @{ from = 'Strauss, Henry\Professional Headshot (1).JPEG'; to = 'henry_strauss.jpg' },
  @{ from = 'Tatman, Tyler\Snapchat-1566615067.jpg';      to = 'tyler_tatman.jpg'   },
  @{ from = 'Nagra, Brayden\IMG_1739.jpeg';               to = 'brayden_nagra.jpg'  },
  @{ from = 'Darmody, Michael\5BD4A0FD-9A3F-4D81-AFA8-83C44C1E3856_1_105_c.jpeg'; to = 'michael_darmody.jpg' },
  @{ from = 'Fritz, Will\cf09a560-a1e9-47ed-a990-077b7514b0d1.jpg'; to = 'will_fritz.jpg' },
  @{ from = 'Carroll, Colin\100444349_8039o7eka6 (1) (1).jpg'; to = 'colin_carroll.jpg' },
  @{ from = 'Modha, Neel\headshot.png';                    to = 'neel_modha.jpg'      }
)

$codec = [System.Drawing.Imaging.ImageCodecInfo]::GetImageEncoders() | Where-Object { $_.MimeType -eq 'image/jpeg' }
$params = New-Object System.Drawing.Imaging.EncoderParameters 1
$params.Param[0] = New-Object System.Drawing.Imaging.EncoderParameter ([System.Drawing.Imaging.Encoder]::Quality), 88L

$MAXLONG = 1400

foreach ($m in $map) {
  $inPath = Join-Path $src $m.from
  if (-not (Test-Path $inPath)) { Write-Output ("MISSING  " + $m.from); continue }
  $img = [System.Drawing.Image]::FromFile($inPath)

  # honour EXIF orientation (tag 0x0112) so phone photos land upright
  if ($img.PropertyIdList -contains 0x0112) {
    $o = $img.GetPropertyItem(0x0112).Value[0]
    switch ($o) {
      3 { $img.RotateFlip([System.Drawing.RotateFlipType]::Rotate180FlipNone) }
      6 { $img.RotateFlip([System.Drawing.RotateFlipType]::Rotate90FlipNone) }
      8 { $img.RotateFlip([System.Drawing.RotateFlipType]::Rotate270FlipNone) }
    }
  }

  $scale = [math]::Min(1.0, $MAXLONG / [math]::Max($img.Width, $img.Height))
  $w = [int][math]::Round($img.Width * $scale)
  $h = [int][math]::Round($img.Height * $scale)

  $bmp = New-Object System.Drawing.Bitmap $w, $h
  $bmp.SetResolution(72, 72)
  $g = [System.Drawing.Graphics]::FromImage($bmp)
  $g.CompositingQuality = [System.Drawing.Drawing2D.CompositingQuality]::HighQuality
  $g.InterpolationMode  = [System.Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic
  $g.SmoothingMode      = [System.Drawing.Drawing2D.SmoothingMode]::HighQuality
  $g.PixelOffsetMode    = [System.Drawing.Drawing2D.PixelOffsetMode]::HighQuality
  $g.Clear([System.Drawing.Color]::White)
  $g.DrawImage($img, (New-Object System.Drawing.Rectangle 0, 0, $w, $h))
  $g.Dispose()

  $outPath = Join-Path $dest $m.to
  $bmp.Save($outPath, $codec, $params)
  $bmp.Dispose()
  $img.Dispose()

  $kb = [int]((Get-Item $outPath).Length / 1kb)
  Write-Output ("OK  {0,-20} {1}x{2}  {3}KB" -f $m.to, $w, $h, $kb)
}

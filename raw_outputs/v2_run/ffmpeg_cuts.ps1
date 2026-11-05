$VideoDir = if ($env:VIDEO_DIR) { $env:VIDEO_DIR } else { ".\video" }
$OutDir = if ($env:OUT_DIR) { $env:OUT_DIR } else { ".\promo_cuts" }
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null

ffmpeg -y -ss 84.00 -to 135.50 -i "$VideoDir\episode-003.mp4" -c:v libx264 -c:a aac "$OutDir\promo01_part1.mp4"
@("file 'promo01_part1.mp4'") | Set-Content -Encoding ascii "$OutDir\promo01.txt"
ffmpeg -y -f concat -safe 0 -i "$OutDir\promo01.txt" -c copy "$OutDir\promo01.mp4"

ffmpeg -y -ss 89.50 -to 133.80 -i "$VideoDir\episode-001.mp4" -c:v libx264 -c:a aac "$OutDir\promo02_part1.mp4"
@("file 'promo02_part1.mp4'") | Set-Content -Encoding ascii "$OutDir\promo02.txt"
ffmpeg -y -f concat -safe 0 -i "$OutDir\promo02.txt" -c copy "$OutDir\promo02.mp4"

ffmpeg -y -ss 16.80 -to 75.30 -i "$VideoDir\episode-011.mp4" -c:v libx264 -c:a aac "$OutDir\promo03_part1.mp4"
@("file 'promo03_part1.mp4'") | Set-Content -Encoding ascii "$OutDir\promo03.txt"
ffmpeg -y -f concat -safe 0 -i "$OutDir\promo03.txt" -c copy "$OutDir\promo03.mp4"

ffmpeg -y -ss 122.80 -to 145.20 -i "$VideoDir\episode-027.mp4" -c:v libx264 -c:a aac "$OutDir\promo04_part1.mp4"
@("file 'promo04_part1.mp4'") | Set-Content -Encoding ascii "$OutDir\promo04.txt"
ffmpeg -y -f concat -safe 0 -i "$OutDir\promo04.txt" -c copy "$OutDir\promo04.mp4"

ffmpeg -y -ss 26.80 -to 69.50 -i "$VideoDir\episode-012.mp4" -c:v libx264 -c:a aac "$OutDir\promo05_part1.mp4"
@("file 'promo05_part1.mp4'") | Set-Content -Encoding ascii "$OutDir\promo05.txt"
ffmpeg -y -f concat -safe 0 -i "$OutDir\promo05.txt" -c copy "$OutDir\promo05.mp4"

ffmpeg -y -ss 54.00 -to 105.50 -i "$VideoDir\episode-005.mp4" -c:v libx264 -c:a aac "$OutDir\promo06_part1.mp4"
@("file 'promo06_part1.mp4'") | Set-Content -Encoding ascii "$OutDir\promo06.txt"
ffmpeg -y -f concat -safe 0 -i "$OutDir\promo06.txt" -c copy "$OutDir\promo06.mp4"

ffmpeg -y -ss 37.40 -to 88.80 -i "$VideoDir\episode-029.mp4" -c:v libx264 -c:a aac "$OutDir\promo07_part1.mp4"
@("file 'promo07_part1.mp4'") | Set-Content -Encoding ascii "$OutDir\promo07.txt"
ffmpeg -y -f concat -safe 0 -i "$OutDir\promo07.txt" -c copy "$OutDir\promo07.mp4"

ffmpeg -y -ss 18.80 -to 62.00 -i "$VideoDir\episode-015.mp4" -c:v libx264 -c:a aac "$OutDir\promo08_part1.mp4"
@("file 'promo08_part1.mp4'") | Set-Content -Encoding ascii "$OutDir\promo08.txt"
ffmpeg -y -f concat -safe 0 -i "$OutDir\promo08.txt" -c copy "$OutDir\promo08.mp4"

ffmpeg -y -ss 32.50 -to 90.10 -i "$VideoDir\episode-024.mp4" -c:v libx264 -c:a aac "$OutDir\promo09_part1.mp4"
@("file 'promo09_part1.mp4'") | Set-Content -Encoding ascii "$OutDir\promo09.txt"
ffmpeg -y -f concat -safe 0 -i "$OutDir\promo09.txt" -c copy "$OutDir\promo09.mp4"

ffmpeg -y -ss 0.00 -to 30.60 -i "$VideoDir\episode-002.mp4" -c:v libx264 -c:a aac "$OutDir\promo10_part1.mp4"
@("file 'promo10_part1.mp4'") | Set-Content -Encoding ascii "$OutDir\promo10.txt"
ffmpeg -y -f concat -safe 0 -i "$OutDir\promo10.txt" -c copy "$OutDir\promo10.mp4"

ffmpeg -y -ss 24.20 -to 53.50 -i "$VideoDir\episode-013.mp4" -c:v libx264 -c:a aac "$OutDir\promo11_part1.mp4"
@("file 'promo11_part1.mp4'") | Set-Content -Encoding ascii "$OutDir\promo11.txt"
ffmpeg -y -f concat -safe 0 -i "$OutDir\promo11.txt" -c copy "$OutDir\promo11.mp4"

ffmpeg -y -ss 22.00 -to 75.50 -i "$VideoDir\episode-007.mp4" -c:v libx264 -c:a aac "$OutDir\promo12_part1.mp4"
@("file 'promo12_part1.mp4'") | Set-Content -Encoding ascii "$OutDir\promo12.txt"
ffmpeg -y -f concat -safe 0 -i "$OutDir\promo12.txt" -c copy "$OutDir\promo12.mp4"

ffmpeg -y -ss 68.80 -to 112.80 -i "$VideoDir\episode-043.mp4" -c:v libx264 -c:a aac "$OutDir\promo13_part1.mp4"
@("file 'promo13_part1.mp4'") | Set-Content -Encoding ascii "$OutDir\promo13.txt"
ffmpeg -y -f concat -safe 0 -i "$OutDir\promo13.txt" -c copy "$OutDir\promo13.mp4"

ffmpeg -y -ss 37.70 -to 97.40 -i "$VideoDir\episode-028.mp4" -c:v libx264 -c:a aac "$OutDir\promo14_part1.mp4"
@("file 'promo14_part1.mp4'") | Set-Content -Encoding ascii "$OutDir\promo14.txt"
ffmpeg -y -f concat -safe 0 -i "$OutDir\promo14.txt" -c copy "$OutDir\promo14.mp4"

ffmpeg -y -ss 63.00 -to 98.41 -i "$VideoDir\episode-039.mp4" -c:v libx264 -c:a aac "$OutDir\promo15_part1.mp4"
@("file 'promo15_part1.mp4'") | Set-Content -Encoding ascii "$OutDir\promo15.txt"
ffmpeg -y -f concat -safe 0 -i "$OutDir\promo15.txt" -c copy "$OutDir\promo15.mp4"

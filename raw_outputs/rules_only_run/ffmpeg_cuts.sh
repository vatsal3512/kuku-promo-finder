#!/usr/bin/env bash
set -euo pipefail
VIDEO_DIR="${VIDEO_DIR:-./video}"
OUT_DIR="${OUT_DIR:-./promo_cuts}"
mkdir -p "$OUT_DIR"

ffmpeg -y -ss 76.80 -to 134.50 -i "$VIDEO_DIR/episode-028.mp4" -c:v libx264 -c:a aac "$OUT_DIR/promo01_part1.mp4"
printf "file '%s'\n" promo01_part1.mp4 > "$OUT_DIR/promo01.txt"
ffmpeg -y -f concat -safe 0 -i "$OUT_DIR/promo01.txt" -c copy "$OUT_DIR/promo01.mp4"

ffmpeg -y -ss 34.90 -to 80.80 -i "$VIDEO_DIR/episode-027.mp4" -c:v libx264 -c:a aac "$OUT_DIR/promo02_part1.mp4"
printf "file '%s'\n" promo02_part1.mp4 > "$OUT_DIR/promo02.txt"
ffmpeg -y -f concat -safe 0 -i "$OUT_DIR/promo02.txt" -c copy "$OUT_DIR/promo02.mp4"

ffmpeg -y -ss 80.10 -to 128.50 -i "$VIDEO_DIR/episode-001.mp4" -c:v libx264 -c:a aac "$OUT_DIR/promo03_part1.mp4"
printf "file '%s'\n" promo03_part1.mp4 > "$OUT_DIR/promo03.txt"
ffmpeg -y -f concat -safe 0 -i "$OUT_DIR/promo03.txt" -c copy "$OUT_DIR/promo03.mp4"

ffmpeg -y -ss 13.60 -to 56.20 -i "$VIDEO_DIR/episode-003.mp4" -c:v libx264 -c:a aac "$OUT_DIR/promo04_part1.mp4"
printf "file '%s'\n" promo04_part1.mp4 > "$OUT_DIR/promo04.txt"
ffmpeg -y -f concat -safe 0 -i "$OUT_DIR/promo04.txt" -c copy "$OUT_DIR/promo04.mp4"

ffmpeg -y -ss 54.00 -to 108.80 -i "$VIDEO_DIR/episode-045.mp4" -c:v libx264 -c:a aac "$OUT_DIR/promo05_part1.mp4"
printf "file '%s'\n" promo05_part1.mp4 > "$OUT_DIR/promo05.txt"
ffmpeg -y -f concat -safe 0 -i "$OUT_DIR/promo05.txt" -c copy "$OUT_DIR/promo05.mp4"

ffmpeg -y -ss 114.80 -to 134.80 -i "$VIDEO_DIR/episode-004.mp4" -c:v libx264 -c:a aac "$OUT_DIR/promo06_part1.mp4"
printf "file '%s'\n" promo06_part1.mp4 > "$OUT_DIR/promo06.txt"
ffmpeg -y -f concat -safe 0 -i "$OUT_DIR/promo06.txt" -c copy "$OUT_DIR/promo06.mp4"

ffmpeg -y -ss 145.80 -to 192.50 -i "$VIDEO_DIR/episode-036.mp4" -c:v libx264 -c:a aac "$OUT_DIR/promo07_part1.mp4"
printf "file '%s'\n" promo07_part1.mp4 > "$OUT_DIR/promo07.txt"
ffmpeg -y -f concat -safe 0 -i "$OUT_DIR/promo07.txt" -c copy "$OUT_DIR/promo07.mp4"

ffmpeg -y -ss 61.80 -to 84.00 -i "$VIDEO_DIR/episode-011.mp4" -c:v libx264 -c:a aac "$OUT_DIR/promo08_part1.mp4"
printf "file '%s'\n" promo08_part1.mp4 > "$OUT_DIR/promo08.txt"
ffmpeg -y -f concat -safe 0 -i "$OUT_DIR/promo08.txt" -c copy "$OUT_DIR/promo08.mp4"

ffmpeg -y -ss 35.30 -to 79.00 -i "$VIDEO_DIR/episode-001.mp4" -c:v libx264 -c:a aac "$OUT_DIR/promo09_part1.mp4"
printf "file '%s'\n" promo09_part1.mp4 > "$OUT_DIR/promo09.txt"
ffmpeg -y -f concat -safe 0 -i "$OUT_DIR/promo09.txt" -c copy "$OUT_DIR/promo09.mp4"

ffmpeg -y -ss 78.00 -to 133.50 -i "$VIDEO_DIR/episode-046.mp4" -c:v libx264 -c:a aac "$OUT_DIR/promo10_part1.mp4"
printf "file '%s'\n" promo10_part1.mp4 > "$OUT_DIR/promo10.txt"
ffmpeg -y -f concat -safe 0 -i "$OUT_DIR/promo10.txt" -c copy "$OUT_DIR/promo10.mp4"

ffmpeg -y -ss 37.40 -to 96.10 -i "$VIDEO_DIR/episode-029.mp4" -c:v libx264 -c:a aac "$OUT_DIR/promo11_part1.mp4"
printf "file '%s'\n" promo11_part1.mp4 > "$OUT_DIR/promo11.txt"
ffmpeg -y -f concat -safe 0 -i "$OUT_DIR/promo11.txt" -c copy "$OUT_DIR/promo11.mp4"

ffmpeg -y -ss 14.30 -to 46.60 -i "$VIDEO_DIR/episode-011.mp4" -c:v libx264 -c:a aac "$OUT_DIR/promo12_part1.mp4"
printf "file '%s'\n" promo12_part1.mp4 > "$OUT_DIR/promo12.txt"
ffmpeg -y -f concat -safe 0 -i "$OUT_DIR/promo12.txt" -c copy "$OUT_DIR/promo12.mp4"

ffmpeg -y -ss 17.90 -to 72.50 -i "$VIDEO_DIR/episode-042.mp4" -c:v libx264 -c:a aac "$OUT_DIR/promo13_part1.mp4"
printf "file '%s'\n" promo13_part1.mp4 > "$OUT_DIR/promo13.txt"
ffmpeg -y -f concat -safe 0 -i "$OUT_DIR/promo13.txt" -c copy "$OUT_DIR/promo13.mp4"

ffmpeg -y -ss 53.50 -to 73.50 -i "$VIDEO_DIR/episode-015.mp4" -c:v libx264 -c:a aac "$OUT_DIR/promo14_part1.mp4"
printf "file '%s'\n" promo14_part1.mp4 > "$OUT_DIR/promo14.txt"
ffmpeg -y -f concat -safe 0 -i "$OUT_DIR/promo14.txt" -c copy "$OUT_DIR/promo14.mp4"

ffmpeg -y -ss 89.80 -to 140.80 -i "$VIDEO_DIR/episode-035.mp4" -c:v libx264 -c:a aac "$OUT_DIR/promo15_part1.mp4"
printf "file '%s'\n" promo15_part1.mp4 > "$OUT_DIR/promo15.txt"
ffmpeg -y -f concat -safe 0 -i "$OUT_DIR/promo15.txt" -c copy "$OUT_DIR/promo15.mp4"

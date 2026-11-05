#!/usr/bin/env bash
set -euo pipefail
VIDEO_DIR="${VIDEO_DIR:-./video}"
OUT_DIR="${OUT_DIR:-./promo_cuts}"
mkdir -p "$OUT_DIR"

ffmpeg -y -ss 84.00 -to 135.50 -i "$VIDEO_DIR/episode-003.mp4" -c:v libx264 -c:a aac "$OUT_DIR/promo01_part1.mp4"
printf "file '%s'\n" promo01_part1.mp4 > "$OUT_DIR/promo01.txt"
ffmpeg -y -f concat -safe 0 -i "$OUT_DIR/promo01.txt" -c copy "$OUT_DIR/promo01.mp4"

ffmpeg -y -ss 89.50 -to 133.80 -i "$VIDEO_DIR/episode-001.mp4" -c:v libx264 -c:a aac "$OUT_DIR/promo02_part1.mp4"
printf "file '%s'\n" promo02_part1.mp4 > "$OUT_DIR/promo02.txt"
ffmpeg -y -f concat -safe 0 -i "$OUT_DIR/promo02.txt" -c copy "$OUT_DIR/promo02.mp4"

ffmpeg -y -ss 16.80 -to 75.30 -i "$VIDEO_DIR/episode-011.mp4" -c:v libx264 -c:a aac "$OUT_DIR/promo03_part1.mp4"
printf "file '%s'\n" promo03_part1.mp4 > "$OUT_DIR/promo03.txt"
ffmpeg -y -f concat -safe 0 -i "$OUT_DIR/promo03.txt" -c copy "$OUT_DIR/promo03.mp4"

ffmpeg -y -ss 122.80 -to 145.20 -i "$VIDEO_DIR/episode-027.mp4" -c:v libx264 -c:a aac "$OUT_DIR/promo04_part1.mp4"
printf "file '%s'\n" promo04_part1.mp4 > "$OUT_DIR/promo04.txt"
ffmpeg -y -f concat -safe 0 -i "$OUT_DIR/promo04.txt" -c copy "$OUT_DIR/promo04.mp4"

ffmpeg -y -ss 26.80 -to 69.50 -i "$VIDEO_DIR/episode-012.mp4" -c:v libx264 -c:a aac "$OUT_DIR/promo05_part1.mp4"
printf "file '%s'\n" promo05_part1.mp4 > "$OUT_DIR/promo05.txt"
ffmpeg -y -f concat -safe 0 -i "$OUT_DIR/promo05.txt" -c copy "$OUT_DIR/promo05.mp4"

ffmpeg -y -ss 54.00 -to 105.50 -i "$VIDEO_DIR/episode-005.mp4" -c:v libx264 -c:a aac "$OUT_DIR/promo06_part1.mp4"
printf "file '%s'\n" promo06_part1.mp4 > "$OUT_DIR/promo06.txt"
ffmpeg -y -f concat -safe 0 -i "$OUT_DIR/promo06.txt" -c copy "$OUT_DIR/promo06.mp4"

ffmpeg -y -ss 37.40 -to 88.80 -i "$VIDEO_DIR/episode-029.mp4" -c:v libx264 -c:a aac "$OUT_DIR/promo07_part1.mp4"
printf "file '%s'\n" promo07_part1.mp4 > "$OUT_DIR/promo07.txt"
ffmpeg -y -f concat -safe 0 -i "$OUT_DIR/promo07.txt" -c copy "$OUT_DIR/promo07.mp4"

ffmpeg -y -ss 18.80 -to 62.00 -i "$VIDEO_DIR/episode-015.mp4" -c:v libx264 -c:a aac "$OUT_DIR/promo08_part1.mp4"
printf "file '%s'\n" promo08_part1.mp4 > "$OUT_DIR/promo08.txt"
ffmpeg -y -f concat -safe 0 -i "$OUT_DIR/promo08.txt" -c copy "$OUT_DIR/promo08.mp4"

ffmpeg -y -ss 32.50 -to 90.10 -i "$VIDEO_DIR/episode-024.mp4" -c:v libx264 -c:a aac "$OUT_DIR/promo09_part1.mp4"
printf "file '%s'\n" promo09_part1.mp4 > "$OUT_DIR/promo09.txt"
ffmpeg -y -f concat -safe 0 -i "$OUT_DIR/promo09.txt" -c copy "$OUT_DIR/promo09.mp4"

ffmpeg -y -ss 0.00 -to 30.60 -i "$VIDEO_DIR/episode-002.mp4" -c:v libx264 -c:a aac "$OUT_DIR/promo10_part1.mp4"
printf "file '%s'\n" promo10_part1.mp4 > "$OUT_DIR/promo10.txt"
ffmpeg -y -f concat -safe 0 -i "$OUT_DIR/promo10.txt" -c copy "$OUT_DIR/promo10.mp4"

ffmpeg -y -ss 24.20 -to 53.50 -i "$VIDEO_DIR/episode-013.mp4" -c:v libx264 -c:a aac "$OUT_DIR/promo11_part1.mp4"
printf "file '%s'\n" promo11_part1.mp4 > "$OUT_DIR/promo11.txt"
ffmpeg -y -f concat -safe 0 -i "$OUT_DIR/promo11.txt" -c copy "$OUT_DIR/promo11.mp4"

ffmpeg -y -ss 22.00 -to 75.50 -i "$VIDEO_DIR/episode-007.mp4" -c:v libx264 -c:a aac "$OUT_DIR/promo12_part1.mp4"
printf "file '%s'\n" promo12_part1.mp4 > "$OUT_DIR/promo12.txt"
ffmpeg -y -f concat -safe 0 -i "$OUT_DIR/promo12.txt" -c copy "$OUT_DIR/promo12.mp4"

ffmpeg -y -ss 68.80 -to 112.80 -i "$VIDEO_DIR/episode-043.mp4" -c:v libx264 -c:a aac "$OUT_DIR/promo13_part1.mp4"
printf "file '%s'\n" promo13_part1.mp4 > "$OUT_DIR/promo13.txt"
ffmpeg -y -f concat -safe 0 -i "$OUT_DIR/promo13.txt" -c copy "$OUT_DIR/promo13.mp4"

ffmpeg -y -ss 37.70 -to 97.40 -i "$VIDEO_DIR/episode-028.mp4" -c:v libx264 -c:a aac "$OUT_DIR/promo14_part1.mp4"
printf "file '%s'\n" promo14_part1.mp4 > "$OUT_DIR/promo14.txt"
ffmpeg -y -f concat -safe 0 -i "$OUT_DIR/promo14.txt" -c copy "$OUT_DIR/promo14.mp4"

ffmpeg -y -ss 63.00 -to 98.41 -i "$VIDEO_DIR/episode-039.mp4" -c:v libx264 -c:a aac "$OUT_DIR/promo15_part1.mp4"
printf "file '%s'\n" promo15_part1.mp4 > "$OUT_DIR/promo15.txt"
ffmpeg -y -f concat -safe 0 -i "$OUT_DIR/promo15.txt" -c copy "$OUT_DIR/promo15.mp4"

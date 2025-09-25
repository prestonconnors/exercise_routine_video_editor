#!/usr/bin/env python3
r"""
Download highest-quality audio from YouTube for Rekordbox 6.

Strategy:
- If the best audio is AAC/M4A: keep it as-is (no re-encode) → .m4a
- Otherwise (typically Opus/WebM): convert once to FLAC (lossless) → .flac
- Embed metadata and thumbnail art for both paths.

Requirements:
- Python 3.8+
- pip install yt-dlp
- FFmpeg must be on PATH (yt-dlp uses it for embedding/convert)

Usage examples:
  python download_music_from_youtube_playlists.py "C:\tmp\yt-cache" "C:\Users\<you>\Music\Rekordbox" https://www.youtube.com/watch?v=ijvLnuf26w8
  python download_music_from_youtube_playlists.py "C:\tmp\yt-cache" "D:\Music\Rekordbox" https://www.youtube.com/playlist?list=XXXXXXXX

Notes:
- The first positional argument (video_output_dir) is accepted for backward compatibility but not used.
- Files are created directly in music_output_dir.
"""

import argparse
import sys
from pathlib import Path
from typing import Dict, Any

try:
    from yt_dlp import YoutubeDL
except Exception as e:
    print("ERROR: yt-dlp is not installed. Try:  pip install yt-dlp", file=sys.stderr)
    raise

def build_opts_keep_m4a(out_dir: Path) -> Dict[str, Any]:
    # Keep AAC/M4A, just remux/copy as needed, embed tags & cover
    return {
        "format": "bestaudio[ext=m4a]/bestaudio[acodec^=aac]/bestaudio",
        "paths": {"home": str(out_dir)},
        "outtmpl": {"default": "%(title)s [%(id)s].%(ext)s"},
        "windowsfilenames": True,
        "overwrites": False,
        "ignoreerrors": "only_download",
        "writethumbnail": True,
        "postprocessors": [
            {"key": "FFmpegThumbnailsConvertor", "format": "jpg"},
            {"key": "FFmpegMetadata"},
            {"key": "EmbedThumbnail"},
        ],
        # Ensure we don't re-encode when ext is already m4a/aac
        "postprocessor_args": {
            "FFmpegMetadata": [],
            "EmbedThumbnail": [],
        },
        # Progress/logging
        "noprogress": False,
        "quiet": False,
        "consoletitle": False,
    }

def build_opts_flac(out_dir: Path) -> Dict[str, Any]:
    # Convert to FLAC (lossless), embed tags & cover
    return {
        "format": "bestaudio/best",
        "paths": {"home": str(out_dir)},
        "outtmpl": {"default": "%(id)s.%(ext)s"},
        "windowsfilenames": True,
        "overwrites": False,
        "ignoreerrors": "only_download",
        "writethumbnail": True,
        "postprocessors": [
            {"key": "FFmpegThumbnailsConvertor", "format": "jpg"},
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "flac",
                "preferredquality": "0",  # ignored for flac, kept for compatibility
            },
            {"key": "FFmpegMetadata"},
            {"key": "EmbedThumbnail"},
        ],
        "noprogress": False,
        "quiet": False,
        "consoletitle": False,
    }

def probe_best_audio_codec(url: str) -> str:
    # Use a lightweight info extraction to decide the path
    probe_opts = {
        "format": "bestaudio/best",
        "skip_download": True,
        "quiet": True,
        "noprogress": True,
        "ignoreerrors": True,
        "extract_flat": False,
    }
    with YoutubeDL(probe_opts) as ydl:
        info = ydl.extract_info(url, download=False)
    # If playlist, take the extractor key or first entry
    if info is None:
        return ""
    # For playlists, info may have 'entries'
    if "entries" in info and info["entries"]:
        # Find the first valid entry with acodec/ext
        for entry in info["entries"]:
            if not entry:
                continue
            acodec = (entry.get("acodec") or "").lower()
            ext = (entry.get("ext") or "").lower()
            if acodec or ext:
                return acodec or ext
        return ""
    # Single video
    return (info.get("acodec") or info.get("ext") or "").lower()

def main() -> int:
    parser = argparse.ArgumentParser(description="Download highest-quality audio for Rekordbox (M4A when source is AAC, FLAC otherwise).")
    parser.add_argument("music_output_dir", help="Destination folder for audio files")
    parser.add_argument("urls", nargs="+", help="One or more YouTube video/playlist URLs")
    args = parser.parse_args()

    out_dir = Path(args.music_output_dir).expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    exit_code = 0

    for url in args.urls:
        try:
            acodec_or_ext = probe_best_audio_codec(url)
            # Heuristic: treat AAC/M4A as copy-keep; everything else → FLAC
            if "aac" in acodec_or_ext or acodec_or_ext.endswith("m4a"):
                opts = build_opts_keep_m4a(out_dir)
                print(f"[info] {url} → keeping AAC/M4A when available (no re-encode)")
            else:
                opts = build_opts_flac(out_dir)
                print(f"[info] {url} → converting to FLAC (lossless)")
            with YoutubeDL(opts) as ydl:
                ydl.download([url])
        except Exception as e:
            print(f"[error] Failed for {url}: {e}", file=sys.stderr)
            exit_code = 1

    print(f"[done] Output folder: {out_dir}")
    return exit_code

if __name__ == "__main__":
    raise SystemExit(main())

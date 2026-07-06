# backend_api/scripts/export_normal_rvc_dataset.py
#
# This script prepares your first "normal tone" voice-conversion dataset.
#
# Beginner explanation:
# This script does NOT train the model.
# This script does NOT call OpenAI.
# This script does NOT change the Angular app.
#
# It only takes your clean short uncle voice clips and exports them into a
# simple RVC-friendly folder:
#
# data/voice_dataset/exports/rvc_normal/wavs/
#
# Your current local source folder is expected to look like:
#
# data/voice_dataset/cleaned_voice_only/
#   s1 e1/
#   s1 e2/
#   s1 e5/
#   s1 e6/
#
# Inside those folders you already have short clean clips.
#
# For now, we are ignoring happy/sad/punchline and treating every clip as:
# normal/original tone.
#
# Why convert to WAV?
# RVC-style tools usually work best when the dataset is clean and consistent.
# This script uses ffmpeg to convert each source clip into:
# - WAV
# - mono
# - 44100 Hz
# - 16-bit PCM

from __future__ import annotations

import argparse
import csv
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import av

# backend_api folder
BACKEND_ROOT = Path(__file__).resolve().parent.parent

# Dataset folders
DATASET_ROOT = BACKEND_ROOT / "data" / "voice_dataset"
DEFAULT_SOURCE_DIR = DATASET_ROOT / "cleaned_voice_only"
DEFAULT_EXPORT_ROOT = DATASET_ROOT / "exports" / "rvc_normal"
DEFAULT_EXPORT_WAVS_DIR = DEFAULT_EXPORT_ROOT / "wavs"
DEFAULT_REPORTS_DIR = DATASET_ROOT / "reports"

# Audio extensions we accept as source files.
SUPPORTED_AUDIO_EXTENSIONS = {
    ".wav",
    ".mp3",
    ".m4a",
    ".webm",
    ".ogg",
    ".mp4",
    ".mpeg",
    ".mpga",
    ".flac",
}

MANIFEST_FIELDS = [
    "exported_file",
    "source_file",
    "duration_seconds",
    "sample_rate",
    "tone",
    "status",
    "warning",
]


@dataclass
class AudioInfo:
    """
    Small DTO-style object for audio info.

    Java comparison:
    This is similar to a simple POJO with:
    - durationSeconds
    - sampleRate
    """

    duration_seconds: float | None
    sample_rate: int | None


@dataclass
class ExportResult:
    """
    DTO-style object for one exported audio file.
    """

    exported_file: str
    source_file: str
    duration_seconds: float | None
    sample_rate: int | None
    tone: str
    status: str
    warning: str


def get_audio_info(audio_path: Path) -> AudioInfo:
    """
    Read audio duration and sample rate using PyAV.

    If PyAV cannot read the file, we do not crash immediately.
    We return None values and report the warning later.
    """
    container = None

    try:
        container = av.open(str(audio_path))

        duration_seconds: float | None = None
        sample_rate: int | None = None

        if container.duration is not None:
            # PyAV stores container.duration in FFmpeg time units.
            # Multiplying by av.time_base converts it into seconds.
            duration_seconds = float(container.duration * av.time_base)

        audio_stream = next(
            (stream for stream in container.streams if stream.type == "audio"),
            None,
        )

        if audio_stream is not None:
            if duration_seconds is None:
                if (
                    audio_stream.duration is not None
                    and audio_stream.time_base is not None
                ):
                    duration_seconds = float(
                        audio_stream.duration * audio_stream.time_base
                    )

            if audio_stream.rate is not None:
                sample_rate = int(audio_stream.rate)

        return AudioInfo(
            duration_seconds=duration_seconds,
            sample_rate=sample_rate,
        )

    except Exception:
        return AudioInfo(duration_seconds=None, sample_rate=None)

    finally:
        if container is not None:
            container.close()


def check_ffmpeg_available() -> None:
    """
    Make sure ffmpeg is installed.

    On Mac, install with:
        brew install ffmpeg

    Why:
    We use ffmpeg to convert mp3/m4a/etc. into consistent WAV files.
    """
    ffmpeg_path = shutil.which("ffmpeg")

    if ffmpeg_path is None:
        raise RuntimeError(
            "ffmpeg was not found. Install it first with: brew install ffmpeg"
        )


def is_hidden_or_junk_file(path: Path) -> bool:
    """
    Skip files like .DS_Store and hidden macOS files.
    """
    return path.name.startswith(".")


def is_supported_audio_file(path: Path) -> bool:
    """
    Return True if this file extension is a supported audio type.
    """
    return (
        path.is_file()
        and not is_hidden_or_junk_file(path)
        and path.suffix.lower() in SUPPORTED_AUDIO_EXTENSIONS
    )


def find_source_audio_files(
    source_dir: Path,
    include_root_files: bool,
) -> list[Path]:
    """
    Recursively find clean source clips.

    By default, we skip files directly inside cleaned_voice_only/.

    Why:
    You have merged files like 16minsAudio.m4a at the root.
    We do not want to accidentally export that long merged file.

    We do want files inside subfolders:
        cleaned_voice_only/s1 e1/*.mp3
        cleaned_voice_only/s1 e2/*.mp3
    """
    if not source_dir.exists():
        raise FileNotFoundError(f"Source folder does not exist: {source_dir}")

    audio_files: list[Path] = []

    for path in source_dir.rglob("*"):
        if not is_supported_audio_file(path):
            continue

        if not include_root_files and path.parent == source_dir:
            continue

        audio_files.append(path)

    return sorted(audio_files)


def make_export_file_name(index: int, source_path: Path, prefix: str) -> str:
    """
    Build a clean exported WAV filename.

    Example:
        uncle_normal_0001.wav
    """
    return f"{prefix}_{index:04d}.wav"


def convert_to_wav(
    source_path: Path,
    output_path: Path,
) -> None:
    """
    Convert one source audio file into a consistent WAV file.

    ffmpeg command:
        ffmpeg -y -i input -ac 1 -ar 44100 -sample_fmt s16 output.wav

    Meaning:
        -y              overwrite output file
        -i              input file
        -ac 1           mono
        -ar 44100       44.1 kHz
        -sample_fmt s16 16-bit PCM
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)

    command = [
        "ffmpeg",
        "-y",
        "-i",
        str(source_path),
        "-ac",
        "1",
        "-ar",
        "44100",
        "-sample_fmt",
        "s16",
        str(output_path),
    ]

    completed = subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    if completed.returncode != 0:
        raise RuntimeError(
            "ffmpeg failed for file:\n"
            f"{source_path}\n\n"
            f"ffmpeg error:\n{completed.stderr}"
        )


def build_warning(
    audio_info: AudioInfo,
    min_seconds: float,
    max_seconds: float,
) -> str:
    """
    Build a warning string for suspicious clips.

    Warnings do not stop export.
    They only help you review dataset quality.
    """
    warnings: list[str] = []

    if audio_info.duration_seconds is None:
        warnings.append("Could not read duration.")
    else:
        if audio_info.duration_seconds < min_seconds:
            warnings.append(
                f"Very short clip: {audio_info.duration_seconds:.2f}s."
            )

        if audio_info.duration_seconds > max_seconds:
            warnings.append(
                f"Long clip: {audio_info.duration_seconds:.2f}s."
            )

    if audio_info.sample_rate is None:
        warnings.append("Could not read sample rate.")

    return " ".join(warnings)


def clean_export_folder(export_wavs_dir: Path) -> None:
    """
    Delete old exported WAV files.

    This prevents mixing old exports with new exports.
    """
    if not export_wavs_dir.exists():
        export_wavs_dir.mkdir(parents=True, exist_ok=True)
        return

    for child in export_wavs_dir.iterdir():
        if child.is_file():
            child.unlink()


def write_manifest(
    export_root: Path,
    rows: Iterable[ExportResult],
) -> None:
    """
    Write manifest.csv.

    This gives you a record of which source file became which exported WAV.
    """
    export_root.mkdir(parents=True, exist_ok=True)
    manifest_path = export_root / "manifest.csv"

    with manifest_path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=MANIFEST_FIELDS)
        writer.writeheader()

        for row in rows:
            writer.writerow(
                {
                    "exported_file": row.exported_file,
                    "source_file": row.source_file,
                    "duration_seconds": (
                        f"{row.duration_seconds:.3f}"
                        if row.duration_seconds is not None
                        else ""
                    ),
                    "sample_rate": row.sample_rate or "",
                    "tone": row.tone,
                    "status": row.status,
                    "warning": row.warning,
                }
            )


def write_report(
    reports_dir: Path,
    export_root: Path,
    results: list[ExportResult],
) -> None:
    """
    Write a human-readable report.
    """
    reports_dir.mkdir(parents=True, exist_ok=True)

    exported_count = sum(1 for result in results if result.status == "exported")
    warning_count = sum(1 for result in results if result.warning)

    total_seconds = 0.0

    for result in results:
        if result.duration_seconds is not None:
            total_seconds += result.duration_seconds

    report_lines = [
        "Normal RVC Dataset Export Report",
        "=" * 33,
        f"Export root: {export_root}",
        f"Total source clips: {len(results)}",
        f"Exported clips: {exported_count}",
        f"Clips with warnings: {warning_count}",
        f"Total source duration seconds: {total_seconds:.2f}",
        f"Total source duration minutes: {total_seconds / 60.0:.2f}",
        "",
        "Warnings:",
    ]

    for result in results:
        if result.warning:
            report_lines.append(f"- {result.source_file}: {result.warning}")

    report_text = "\n".join(report_lines)
    report_path = reports_dir / "rvc_normal_export_report.txt"
    report_path.write_text(report_text, encoding="utf-8")

    print(report_text)
    print()
    print(f"Report saved to: {report_path}")


def run_export(
    source_dir: Path,
    export_root: Path,
    include_root_files: bool,
    clean: bool,
    dry_run: bool,
    min_seconds: float,
    max_seconds: float,
    prefix: str,
) -> None:
    """
    Main export flow.

    Steps:
    1. Find clips under cleaned_voice_only subfolders.
    2. Read duration/sample rate.
    3. Convert each clip to WAV.
    4. Write manifest.csv.
    5. Write report.
    """
    check_ffmpeg_available()

    source_dir = source_dir.resolve()
    export_root = export_root.resolve()
    export_wavs_dir = export_root / "wavs"

    audio_files = find_source_audio_files(
        source_dir=source_dir,
        include_root_files=include_root_files,
    )

    if not audio_files:
        print("No source audio files were found.")
        print()
        print(f"Source folder checked: {source_dir}")
        print()
        print("Expected structure:")
        print("  cleaned_voice_only/s1 e1/*.mp3")
        print("  cleaned_voice_only/s1 e2/*.mp3")
        print("  cleaned_voice_only/s1 e5/*.mp3")
        print("  cleaned_voice_only/s1 e6/*.mp3")
        return

    if clean and not dry_run:
        clean_export_folder(export_wavs_dir)

    results: list[ExportResult] = []

    for index, source_path in enumerate(audio_files, start=1):
        audio_info = get_audio_info(source_path)
        warning = build_warning(
            audio_info=audio_info,
            min_seconds=min_seconds,
            max_seconds=max_seconds,
        )

        exported_name = make_export_file_name(
            index=index,
            source_path=source_path,
            prefix=prefix,
        )

        exported_path = export_wavs_dir / exported_name

        source_relative = source_path.relative_to(DATASET_ROOT).as_posix()
        exported_relative = exported_path.relative_to(export_root).as_posix()

        if dry_run:
            status = "dry-run"
        else:
            convert_to_wav(
                source_path=source_path,
                output_path=exported_path,
            )
            status = "exported"

        results.append(
            ExportResult(
                exported_file=exported_relative,
                source_file=source_relative,
                duration_seconds=audio_info.duration_seconds,
                sample_rate=audio_info.sample_rate,
                tone="normal",
                status=status,
                warning=warning,
            )
        )

    if not dry_run:
        write_manifest(
            export_root=export_root,
            rows=results,
        )

    write_report(
        reports_dir=DEFAULT_REPORTS_DIR,
        export_root=export_root,
        results=results,
    )

    print()
    print("Done.")
    print()
    print("Next:")
    print(f"  1. Listen to exported WAV files in: {export_wavs_dir}")
    print("  2. Remove bad clips from your source folder if needed.")
    print("  3. Re-run this script with --clean.")
    print("  4. Use the exported wavs folder for your first RVC training experiment.")


def build_parser() -> argparse.ArgumentParser:
    """
    Build command-line arguments.

    Beginner explanation:
    argparse lets you run this script with options like:
        --dry-run
        --clean
        --include-root-files
    """
    parser = argparse.ArgumentParser(
        description="Export normal-tone uncle voice clips for an RVC-style dataset."
    )

    parser.add_argument(
        "--source-dir",
        default=str(DEFAULT_SOURCE_DIR),
        help="Folder containing clean source clips. Defaults to data/voice_dataset/cleaned_voice_only.",
    )

    parser.add_argument(
        "--export-root",
        default=str(DEFAULT_EXPORT_ROOT),
        help="Export folder. Defaults to data/voice_dataset/exports/rvc_normal.",
    )

    parser.add_argument(
        "--include-root-files",
        action="store_true",
        help="Also include files directly inside cleaned_voice_only. By default, root files are skipped.",
    )

    parser.add_argument(
        "--clean",
        action="store_true",
        help="Delete old exported WAV files before exporting again.",
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be exported without creating WAV files.",
    )

    parser.add_argument(
        "--min-seconds",
        type=float,
        default=0.5,
        help="Warn if a clip is shorter than this many seconds.",
    )

    parser.add_argument(
        "--max-seconds",
        type=float,
        default=15.0,
        help="Warn if a clip is longer than this many seconds.",
    )

    parser.add_argument(
        "--prefix",
        default="uncle_normal",
        help="Prefix for exported WAV files.",
    )

    return parser


def main() -> None:
    """
    Script entry point.
    """
    parser = build_parser()
    args = parser.parse_args()

    try:
        run_export(
            source_dir=Path(args.source_dir),
            export_root=Path(args.export_root),
            include_root_files=args.include_root_files,
            clean=args.clean,
            dry_run=args.dry_run,
            min_seconds=args.min_seconds,
            max_seconds=args.max_seconds,
            prefix=args.prefix,.
        0

        )
    except Exception as exc:
        print()
        print("Export failed.")
        print(str(exc))
        print()
        sys.exit(1)


if __name__ == "__main__":
    main()
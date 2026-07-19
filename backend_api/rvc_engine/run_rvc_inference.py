# backend_api/rvc_engine/run_rvc_inference.py
#
# Phase 3B - Backend-only RVC wrapper script
#
# Beginner explanation:
# Before connecting RVC to FastAPI and Angular, we want one simple script that can:
#
# 1. Take an input audio file
# 2. Use the trained RVC model .pth file
# 3. Use the trained RVC .index file
# 4. Generate a converted output WAV file
#
# This script is meant to run using the RVC virtual environment:
#
#   backend_api/.venv-rvc
#
# Example:
#
#   .\.venv-rvc\Scripts\python.exe .\rvc_engine\run_rvc_inference.py `
#     --input ".\data\rvc_test_inputs\recording_test.wav"
#
# Later, the normal FastAPI backend can call this script automatically.
# That way, the user does not need to manually activate .venv-rvc or type the long RVC command.

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


# backend_api folder
BACKEND_ROOT = Path(__file__).resolve().parent.parent

# Default model folder:
# backend_api/models/rvc/hari_normal_v1
DEFAULT_MODEL_DIR = BACKEND_ROOT / "models" / "rvc" / "hari_normal_v1"

# Your trained model files
DEFAULT_MODEL_PATH = DEFAULT_MODEL_DIR / "hari_normal_v1_100e_11100s.pth"
DEFAULT_INDEX_PATH = DEFAULT_MODEL_DIR / "hari_normal_v1.index"

# Default generated output folder
DEFAULT_OUTPUT_DIR = BACKEND_ROOT / "outputs" / "rvc"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run local RVC voice conversion using the trained hari_normal_v1 model."
    )

    parser.add_argument(
        "--input",
        required=True,
        help="Path to input audio file. WAV is recommended for testing.",
    )

    parser.add_argument(
        "--output",
        required=False,
        help=(
            "Path to output WAV file. "
            "If not provided, output will be created inside backend_api/outputs/rvc."
        ),
    )

    parser.add_argument(
        "--model",
        default=str(DEFAULT_MODEL_PATH),
        help="Path to the trained RVC .pth model file.",
    )

    parser.add_argument(
        "--index",
        default=str(DEFAULT_INDEX_PATH),
        help="Path to the trained RVC .index file.",
    )

    parser.add_argument(
        "--device",
        default="cpu",
        help="Device to use. Use cpu for now. Later, cuda:0 can be used if supported.",
    )

    parser.add_argument(
        "--method",
        default="rmvpe",
        choices=["harvest", "crepe", "rmvpe", "pm"],
        help="Pitch extraction algorithm.",
    )

    parser.add_argument(
        "--version",
        default="v2",
        choices=["v1", "v2"],
        help="RVC model version. Your model was trained as v2.",
    )

    parser.add_argument(
        "--pitch",
        type=int,
        default=6,
        help="Pitch shift in semitones. Try 0, 4, 6, 8, or 10.",
    )

    parser.add_argument(
        "--index-rate",
        type=float,
        default=0.75,
        help="Search feature ratio. Common values: 0.5 to 0.8.",
    )

    parser.add_argument(
        "--protect",
        type=float,
        default=0.5,
        help="Protect voiceless consonants and breath sounds. Common values: 0.33 to 0.5.",
    )

    return parser.parse_args()


def resolve_path(path_value: str) -> Path:
    """
    Convert a user-provided path into an absolute Path.

    If the user gives:
      .\\data\\rvc_test_inputs\\recording_test.wav

    and runs this script from backend_api, this will resolve correctly.

    If the user gives:
      C:\\AI app\\...

    that absolute path also works.
    """
    path = Path(path_value)

    if path.is_absolute():
        return path

    return (Path.cwd() / path).resolve()


def build_default_output_path(input_path: Path) -> Path:
    """
    Build a default output path if the user does not pass --output.

    Example:
      input:
        recording_test.wav

      output:
        backend_api/outputs/rvc/recording_test_rvc.wav
    """
    DEFAULT_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    output_file_name = f"{input_path.stem}_rvc.wav"

    return DEFAULT_OUTPUT_DIR / output_file_name


def validate_file_exists(path: Path, label: str) -> None:
    if not path.exists():
        raise FileNotFoundError(f"{label} was not found: {path}")

    if not path.is_file():
        raise ValueError(f"{label} is not a file: {path}")


def run_rvc_conversion(
    input_path: Path,
    output_path: Path,
    model_path: Path,
    index_path: Path,
    device: str,
    method: str,
    version: str,
    pitch: int,
    index_rate: float,
    protect: float,
) -> None:
    """
    Run the installed rvc-python CLI using the current Python executable.

    Important:
    This script should be run with:
      backend_api/.venv-rvc/Scripts/python.exe

    sys.executable points to that Python executable.
    So this command uses the RVC packages installed in .venv-rvc.
    """

    output_path.parent.mkdir(parents=True, exist_ok=True)

    command = [
        sys.executable,
        "-m",
        "rvc_python",
        "cli",
        "-i",
        str(input_path),
        "-o",
        str(output_path),
        "-mp",
        str(model_path),
        "-ip",
        str(index_path),
        "-v",
        version,
        "-de",
        device,
        "-me",
        method,
        "-pi",
        str(pitch),
        "-ir",
        str(index_rate),
        "-pr",
        str(protect),
    ]

    print("Running RVC conversion...")
    print(f"Input:      {input_path}")
    print(f"Output:     {output_path}")
    print(f"Model:      {model_path}")
    print(f"Index:      {index_path}")
    print(f"Device:     {device}")
    print(f"Method:     {method}")
    print(f"Version:    {version}")
    print(f"Pitch:      {pitch}")
    print(f"Index rate: {index_rate}")
    print(f"Protect:    {protect}")
    print()

    subprocess.run(command, check=True)

    if not output_path.exists():
        raise RuntimeError(f"RVC command finished, but output file was not created: {output_path}")

    print()
    print(f"RVC conversion complete: {output_path}")


def main() -> None:
    args = parse_args()

    input_path = resolve_path(args.input)
    model_path = resolve_path(args.model)
    index_path = resolve_path(args.index)

    if args.output:
      output_path = resolve_path(args.output)
    else:
      output_path = build_default_output_path(input_path)

    validate_file_exists(input_path, "Input audio file")
    validate_file_exists(model_path, "RVC model file")
    validate_file_exists(index_path, "RVC index file")

    run_rvc_conversion(
        input_path=input_path,
        output_path=output_path,
        model_path=model_path,
        index_path=index_path,
        device=args.device,
        method=args.method,
        version=args.version,
        pitch=args.pitch,
        index_rate=args.index_rate,
        protect=args.protect,
    )


if __name__ == "__main__":
    main()
"""Convert downloaded HTML filings to Markdown with Docling.

Run from the repository root with:
    uv run --project backend python data/convert_to_markdown.py
"""
from __future__ import annotations

import argparse
from pathlib import Path

from docling.document_converter import DocumentConverter

DATA_DIR = Path(__file__).resolve().parent
DEFAULT_INPUT_DIR = DATA_DIR / "downloads"
DEFAULT_OUTPUT_DIR = DATA_DIR / "markdown"
HTML_SUFFIXES = {".htm", ".html"}


def html_files(input_dir: Path) -> list[Path]:
    return sorted(
        path
        for path in input_dir.rglob("*")
        if path.is_file() and path.suffix.lower() in HTML_SUFFIXES
    )


def output_path(source_path: Path, input_dir: Path, output_dir: Path) -> Path:
    relative_path = source_path.relative_to(input_dir)
    return (output_dir / relative_path).with_suffix(".md")


def should_convert(source_path: Path, target_path: Path, force: bool) -> bool:
    if force or not target_path.exists():
        return True
    return source_path.stat().st_mtime > target_path.stat().st_mtime


def convert_file(
    converter: DocumentConverter,
    source_path: Path,
    target_path: Path,
) -> None:
    result = converter.convert(source_path)
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_text(result.document.export_to_markdown(), encoding="utf-8")


def convert_directory(input_dir: Path, output_dir: Path, force: bool) -> tuple[int, int, int]:
    if not input_dir.exists():
        raise FileNotFoundError(f"Input directory does not exist: {input_dir}")

    converter = DocumentConverter()
    converted = skipped = failed = 0

    for source_path in html_files(input_dir):
        target_path = output_path(source_path, input_dir, output_dir)
        if not should_convert(source_path, target_path, force):
            skipped += 1
            print(f"Skipping up-to-date file: {source_path.relative_to(input_dir)}")
            continue

        print(f"Converting: {source_path.relative_to(input_dir)}")
        try:
            convert_file(converter, source_path, target_path)
        except Exception as error:  # noqa: BLE001
            failed += 1
            print(f"Failed: {source_path} ({error})")
        else:
            converted += 1

    return converted, skipped, failed


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input-dir",
        type=Path,
        default=DEFAULT_INPUT_DIR,
        help=f"HTML input directory (default: {DEFAULT_INPUT_DIR})",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help=f"Markdown output directory (default: {DEFAULT_OUTPUT_DIR})",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Reconvert files even when the Markdown output is up to date.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    converted, skipped, failed = convert_directory(
        args.input_dir.resolve(), args.output_dir.resolve(), args.force
    )
    print(f"Converted: {converted}; skipped: {skipped}; failed: {failed}")
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()

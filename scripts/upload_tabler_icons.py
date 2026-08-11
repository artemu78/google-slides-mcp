#!/usr/bin/env python3
"""Convert bundled Tabler SVGs to PNG and sync them to S3 safely."""

from __future__ import annotations

import argparse
import concurrent.futures
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python older than 3.11
    tomllib = None  # type: ignore[assignment]


STYLES = ("outline", "filled")
THEME_COLORS = {"dark": "#000000", "light": "#E5E7EB"}
EXPECTED_TOTAL = 6_184
CONFIG_SECTION = "[mcp_servers.s3-uploader.env]"
AWS_CREDENTIAL_KEYS = (
    "AWS_ACCESS_KEY_ID",
    "AWS_SECRET_ACCESS_KEY",
    "AWS_SESSION_TOKEN",
)
AWS_REGION_KEYS = ("AWS_REGION", "AWS_DEFAULT_REGION")
BUCKET_KEYS = ("BUCKET_NAME", "S3_BUCKET", "AWS_S3_BUCKET")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--dry-run",
        action="store_true",
        help="convert locally, then show what aws s3 sync would upload",
    )
    mode.add_argument(
        "--upload",
        action="store_true",
        help="convert locally and perform the real S3 sync",
    )
    parser.add_argument(
        "--cache-dir",
        type=Path,
        default=Path(tempfile.gettempdir()) / "google-slides-mcp-tabler-icons-png",
        help="persistent PNG cache outside the repository (default: %(default)s)",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=min(8, os.cpu_count() or 1),
        help="parallel SVG conversions (default: %(default)s)",
    )
    parser.add_argument(
        "--theme",
        choices=THEME_COLORS,
        default="dark",
        help="PNG theme to render (default: %(default)s)",
    )
    parser.add_argument("--aws-profile", help="Use this local AWS CLI profile instead of MCP credentials.")
    parser.add_argument("--bucket", help="S3 bucket when using --aws-profile.")
    parser.add_argument("--region", help="AWS region when using --aws-profile.")
    return parser.parse_args()


def fail(message: str) -> "NoReturn":
    print(f"Error: {message}", file=sys.stderr)
    raise SystemExit(1)


def find_program(name: str, install_hint: str) -> str:
    path = shutil.which(name)
    if not path:
        fail(f"{name} is required but was not found. {install_hint}")
    return path


def inventory(repo_root: Path) -> dict[str, list[Path]]:
    icons_root = repo_root / "tabler-icons-main" / "icons"
    result: dict[str, list[Path]] = {}
    for style in STYLES:
        source_dir = icons_root / style
        if not source_dir.is_dir():
            fail(f"source directory does not exist: {source_dir}")
        files = sorted(source_dir.glob("*.svg"))
        if not files:
            fail(f"no SVG files found in: {source_dir}")
        result[style] = files

    total = sum(len(files) for files in result.values())
    if total != EXPECTED_TOTAL:
        fail(
            f"expected {EXPECTED_TOTAL:,} SVG files, found {total:,}; "
            "refusing to upload an incomplete or unexpected catalog"
        )
    return result


def load_s3_environment(config_path: Path) -> tuple[dict[str, str], str, str]:
    if tomllib is None:
        fail("Python 3.11 or newer is required to read ~/.codex/config.toml safely")
    if not config_path.is_file():
        fail(f"Codex configuration file does not exist: {config_path}")
    try:
        config = tomllib.loads(config_path.read_text(encoding="utf-8"))
        values = config["mcp_servers"]["s3-uploader"]["env"]
    except (OSError, tomllib.TOMLDecodeError, KeyError, TypeError) as exc:
        fail(f"cannot read {CONFIG_SECTION} from {config_path}: {exc}")

    if not isinstance(values, dict):
        fail(f"{CONFIG_SECTION} must be a TOML table")

    missing_credentials = [key for key in AWS_CREDENTIAL_KEYS[:2] if not values.get(key)]
    if missing_credentials:
        fail(f"{CONFIG_SECTION} is missing required AWS credential fields")

    region = next((str(values[key]) for key in AWS_REGION_KEYS if values.get(key)), "")
    bucket = next((str(values[key]) for key in BUCKET_KEYS if values.get(key)), "")
    if not region:
        fail(f"{CONFIG_SECTION} is missing AWS_REGION")
    if not bucket:
        fail(f"{CONFIG_SECTION} is missing BUCKET_NAME")

    aws_env = os.environ.copy()
    for key in (*AWS_CREDENTIAL_KEYS, *AWS_REGION_KEYS):
        if values.get(key):
            aws_env[key] = str(values[key])
    aws_env["AWS_REGION"] = region
    aws_env["AWS_DEFAULT_REGION"] = region
    return aws_env, region, bucket


def needs_conversion(source: Path, destination: Path) -> bool:
    return not destination.is_file() or destination.stat().st_mtime_ns < source.stat().st_mtime_ns


def convert_one(rsvg: str, source: Path, destination: Path, color: str) -> tuple[bool, str]:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(f".png.tmp-{os.getpid()}-{threading.get_ident()}")
    temporary_svg = destination.with_suffix(f".svg.tmp-{os.getpid()}-{threading.get_ident()}")
    try:
        temporary_svg.write_text(
            source.read_text(encoding="utf-8").replace("currentColor", color),
            encoding="utf-8",
        )
        completed = subprocess.run(
            [
                rsvg,
                "--format",
                "png",
                "--width",
                "96",
                "--height",
                "96",
                "--keep-aspect-ratio",
                "--background-color",
                "rgba(0,0,0,0)",
                "--output",
                str(temporary),
                str(temporary_svg),
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
        if completed.returncode:
            return False, completed.stderr.strip() or f"exit code {completed.returncode}"
        temporary.replace(destination)
        return True, ""
    finally:
        temporary.unlink(missing_ok=True)
        temporary_svg.unlink(missing_ok=True)


def convert_catalog(
    inventory_by_style: dict[str, list[Path]], cache_dir: Path, rsvg: str, workers: int, color: str
) -> tuple[int, int, int]:
    pending: list[tuple[Path, Path]] = []
    skipped = 0
    for style, sources in inventory_by_style.items():
        for source in sources:
            destination = cache_dir / style / f"{source.stem}.png"
            if needs_conversion(source, destination):
                pending.append((source, destination))
            else:
                skipped += 1

    converted = 0
    failures: list[tuple[Path, str]] = []
    if pending:
        print(f"Converting {len(pending):,} SVG files with {workers} workers...")
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
            future_to_source = {
                executor.submit(convert_one, rsvg, source, destination, color): source
                for source, destination in pending
            }
            for completed_count, future in enumerate(
                concurrent.futures.as_completed(future_to_source), start=1
            ):
                source = future_to_source[future]
                try:
                    succeeded, error = future.result()
                except Exception as exc:  # keep processing the remaining catalog
                    succeeded, error = False, str(exc)
                if succeeded:
                    converted += 1
                else:
                    failures.append((source, error))
                if completed_count % 250 == 0 or completed_count == len(pending):
                    print(f"  conversion progress: {completed_count:,}/{len(pending):,}")

    for source, error in failures[:10]:
        print(f"Conversion failed: {source.name}: {error}", file=sys.stderr)
    if len(failures) > 10:
        print(f"...and {len(failures) - 10:,} more conversion failures", file=sys.stderr)
    return converted, skipped, len(failures)


def sync_to_s3(
    aws: str, cache_dir: Path, bucket: str, aws_env: dict[str, str], dry_run: bool, theme: str, profile: str | None
) -> tuple[int, int]:
    command = [
        aws,
        "s3",
        "sync",
        str(cache_dir),
        f"s3://{bucket}/tabler-icons/{theme}/",
        "--exclude",
        "*",
        "--include",
        "*.png",
        "--content-type",
        "image/png",
        "--no-progress",
    ]
    if profile:
        command.extend(["--profile", profile])
    if dry_run:
        command.append("--dryrun")
    print("Checking S3 sync plan..." if dry_run else "Uploading changed PNG files to S3...")
    completed = subprocess.run(
        command,
        env=aws_env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    output_lines = completed.stdout.splitlines()
    uploads = sum("upload:" in line for line in output_lines)
    if dry_run and uploads:
        print(f"Dry run would upload {uploads:,} files.")
    elif not dry_run:
        print(f"AWS CLI reported {uploads:,} uploaded files.")
    if completed.returncode:
        message = completed.stderr.strip() or "AWS CLI sync failed"
        print(f"AWS error: {message}", file=sys.stderr)
    return uploads, completed.returncode


def main() -> int:
    args = parse_args()
    if args.workers < 1:
        fail("--workers must be at least 1")

    repo_root = Path(__file__).resolve().parents[1]
    cache_dir = args.cache_dir.expanduser().resolve()
    try:
        cache_dir.relative_to(repo_root)
    except ValueError:
        pass
    else:
        fail("--cache-dir must be outside the Git repository")

    inventory_by_style = inventory(repo_root)
    total = sum(len(files) for files in inventory_by_style.values())
    print(
        f"Validated sources: {len(inventory_by_style['outline']):,} outline + "
        f"{len(inventory_by_style['filled']):,} filled = {total:,} SVG files"
    )

    rsvg = find_program(
        "rsvg-convert",
        "Install librsvg first (macOS: brew install librsvg; Debian/Ubuntu: sudo apt install librsvg2-bin).",
    )
    aws = find_program("aws", "Install AWS CLI v2 and retry.")
    if args.aws_profile:
        if not args.bucket or not args.region:
            fail("--bucket and --region are required with --aws-profile")
        aws_env, region, bucket = os.environ.copy(), args.region, args.bucket
    else:
        aws_env, region, bucket = load_s3_environment(Path.home() / ".codex" / "config.toml")

    cache_dir = cache_dir / args.theme
    cache_dir.mkdir(parents=True, exist_ok=True)
    converted, skipped, failed = convert_catalog(
        inventory_by_style, cache_dir, rsvg, args.workers, THEME_COLORS[args.theme]
    )
    uploaded = 0
    sync_status = 0
    if failed == 0:
        uploaded, sync_status = sync_to_s3(
            aws, cache_dir, bucket, aws_env, dry_run=args.dry_run, theme=args.theme, profile=args.aws_profile
        )
    else:
        print("Skipping S3 sync because one or more conversions failed.", file=sys.stderr)

    label = "would upload" if args.dry_run else "uploaded"
    print(
        f"Final counts: converted={converted:,}, skipped={skipped:,}, "
        f"failed={failed:,}, {label}={uploaded:,}"
    )
    print(f"Expected theme URL: https://{bucket}.s3.{region}.amazonaws.com/tabler-icons/{args.theme}")
    if args.dry_run:
        print("Dry run complete; no S3 objects were uploaded or deleted.")
    else:
        print("Upload complete; no remote objects were deleted and no ACL was changed.")
    return 1 if failed or sync_status else 0


if __name__ == "__main__":
    raise SystemExit(main())

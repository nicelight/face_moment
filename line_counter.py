#!/usr/bin/env python3

from collections import defaultdict
from pathlib import Path
import os
import sys


ROOT = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()


# ============================================================
# FILE TYPES
# ============================================================

CODE_EXT = {
    ".py",
    ".js", ".mjs", ".cjs",
    ".ts", ".tsx", ".jsx",
    ".svelte", ".vue",
    ".go", ".rs",
    ".java", ".kt",
    ".c", ".cpp", ".h", ".hpp",
    ".cs",
    ".rb",
    ".php",
    ".sh",
}

WEB_EXT = {
    ".css", ".scss", ".html",
}

TEXT_EXT = CODE_EXT | WEB_EXT | {
    ".json", ".jsonl",
    ".yaml", ".yml",
    ".toml",
    ".ini", ".cfg", ".conf",
    ".md", ".mdx", ".rst", ".txt",
    ".sql", ".xml",
    ".env",
    ".lock",
    ".csv",
}

KNOWN_BINARY_EXT = {
    ".onnx",
    ".wasm",
    ".tflite",
    ".pt", ".pth",
    ".bin",
    ".so", ".dll",
    ".a", ".o",
    ".pyc", ".class",

    ".png", ".jpg", ".jpeg",
    ".gif", ".webp", ".ico",

    ".pdf",
    ".zip", ".gz", ".7z", ".tar",

    ".mp4", ".mov", ".avi",
    ".mp3", ".wav",
}


# ============================================================
# DIRECTORIES
# ============================================================

TEST_DIRS = {
    "test",
    "tests",
    "__tests__",
    "spec",
    "specs",
}

# DevRails / Memory Bank infrastructure.
# .tasks is included because these are task artifacts generated
# by the same development workflow.
DEVRAILS_DIRS = {
    ".memory-bank",
    "memory-bank",
    ".protocols",
    "protocols",
    ".tasks",
}

AGENT_DIRS = {
    ".agents",
    ".claude",
    ".codex",
    ".cursor",
    ".roo",
    ".playwright-cli",
    ".depwire",
}

CACHE_DIRS = {
    ".mypy_cache",
    ".pytest_cache",
    "__pycache__",
    ".ruff_cache",
    ".cache",
    "coverage",
    "htmlcov",
    "test-results",
}

VENDOR_DIRS = {
    "node_modules",
    ".venv",
    "venv",
    "vendor",
    "third_party",
    "third-party",
    "dist",
    "build",
}

DOC_DIRS = {
    "docs",
    "doc",
    "mermaids",
    "papercuts",
}

MODEL_DIRS = {
    "models",
    "weights",
    "checkpoints",
}


SPECIAL_TEXT_FILES = {
    "dockerfile",
    "makefile",
    "compose.yaml",
    "compose.yml",
    "docker-compose.yaml",
    "docker-compose.yml",

    "pyproject.toml",
    "package.json",
    "package-lock.json",
    "requirements.txt",

    "alembic.ini",

    ".gitignore",
    ".dockerignore",
    ".env",
    ".env.example",
}


# ============================================================
# HELPERS
# ============================================================

def is_test_file(rel: Path) -> bool:
    parts = {part.lower() for part in rel.parts}
    name = rel.name.lower()

    if parts & TEST_DIRS:
        return True

    patterns = (
        ".test.js",
        ".test.ts",
        ".test.jsx",
        ".test.tsx",
        ".spec.js",
        ".spec.ts",
        ".spec.jsx",
        ".spec.tsx",
    )

    return (
        name.startswith("test_")
        or name.endswith("_test.py")
        or name.endswith(patterns)
    )


def classify(rel: Path) -> str | None:
    parts = {part.lower() for part in rel.parts}
    name = rel.name.lower()
    ext = rel.suffix.lower()

    # Git internals are completely ignored.
    if ".git" in parts:
        return None

    # DevRails must be checked BEFORE tests:
    # files inside .tasks may contain "test" in their names.
    if parts & DEVRAILS_DIRS:
        return "DEVRAILS"

    if is_test_file(rel):
        return "TESTS"

    if parts & CACHE_DIRS:
        return "CACHE"

    if parts & VENDOR_DIRS:
        return "VENDOR_GENERATED"

    if (
        parts & MODEL_DIRS
        or ext in {".onnx", ".wasm", ".tflite", ".pt", ".pth"}
    ):
        return "MODELS_ASSETS"

    if parts & AGENT_DIRS:
        return "AGENT_DEV_ARTIFACTS"

    if parts & DOC_DIRS:
        return "DOCS_SPECS"

    if ext in {".md", ".mdx", ".rst"}:
        return "DOCS_SPECS"

    if "migrations" in parts:
        return "MIGRATIONS"

    if "scripts" in parts:
        return "PROJECT_SCRIPTS"

    if (
        "deploy" in parts
        or name in SPECIAL_TEXT_FILES
        or ext in {".yaml", ".yml", ".toml", ".ini", ".cfg", ".conf"}
    ):
        return "INFRA_CONFIG"

    if ext in CODE_EXT or ext in WEB_EXT:
        return "PROD_CODE"

    return "OTHER"


def is_text_file(path: Path) -> bool:
    ext = path.suffix.lower()
    name = path.name.lower()

    if ext in KNOWN_BINARY_EXT:
        return False

    if ext in TEXT_EXT or name in SPECIAL_TEXT_FILES:
        return True

    # Unknown extension: inspect first 8 KiB.
    try:
        with path.open("rb") as f:
            sample = f.read(8192)
    except OSError:
        return False

    if not sample:
        return True

    if b"\x00" in sample:
        return False

    try:
        sample.decode("utf-8")
        return True
    except UnicodeDecodeError:
        return False


def count_lines(path: Path) -> int:
    """
    Count lines without loading the whole file into RAM.
    Binary files never reach this function.
    """
    count = 0
    last_byte = None

    try:
        with path.open("rb") as f:
            while True:
                chunk = f.read(1024 * 1024)

                if not chunk:
                    break

                count += chunk.count(b"\n")
                last_byte = chunk[-1]

    except OSError:
        return 0

    # File with content but without final newline.
    if path.stat().st_size > 0 and last_byte != ord("\n"):
        count += 1

    return count


# ============================================================
# ANALYZE
# ============================================================

stats = defaultdict(
    lambda: {
        "files": 0,
        "lines": 0,
        "bytes": 0,
    }
)

largest = defaultdict(list)


for base, dirs, files in os.walk(ROOT):

    # Do not even descend into .git.
    dirs[:] = [
        d for d in dirs
        if d != ".git"
    ]

    for filename in files:
        path = Path(base) / filename

        try:
            rel = path.relative_to(ROOT)
        except ValueError:
            continue

        category = classify(rel)

        if category is None:
            continue

        try:
            size = path.stat().st_size
        except OSError:
            continue

        if is_text_file(path):
            lines = count_lines(path)
        else:
            lines = 0

        stats[category]["files"] += 1
        stats[category]["lines"] += lines
        stats[category]["bytes"] += size

        largest[category].append(
            (
                lines,
                size,
                rel.as_posix(),
            )
        )


# ============================================================
# DETAILED REPORT
# ============================================================

ORDER = [
    "PROD_CODE",
    "TESTS",
    "MIGRATIONS",
    "PROJECT_SCRIPTS",
    "INFRA_CONFIG",
    "DEVRAILS",
    "AGENT_DEV_ARTIFACTS",
    "DOCS_SPECS",
    "VENDOR_GENERATED",
    "MODELS_ASSETS",
    "CACHE",
    "OTHER",
]


print()
print(f"Repository: {ROOT}")
print()

print(
    f"{'CATEGORY':24}"
    f"{'FILES':>8}"
    f"{'LINES':>14}"
    f"{'MiB':>12}"
)

print("-" * 58)

for category in ORDER:
    s = stats[category]

    print(
        f"{category:24}"
        f"{s['files']:8d}"
        f"{s['lines']:14,d}"
        f"{s['bytes'] / 1024 / 1024:12.2f}"
    )


# ============================================================
# LARGEST FILES
# ============================================================

print()
print("=== TOP FILES BY CATEGORY ===")

for category in ORDER:
    items = sorted(
        largest[category],
        reverse=True,
    )[:5]

    if not items:
        continue

    print()
    print(f"[{category}]")

    for lines, size, rel in items:
        print(
            f"{lines:10,d} lines  "
            f"{size / 1024 / 1024:8.2f} MiB  "
            f"{rel}"
        )


# ============================================================
# SIMPLE SUMMARY
# ============================================================

#
# CODE:
#   Product source code
#   + DB migrations
#
# PROJECT_SCRIPTS are intentionally NOT automatically included
# because repositories often contain CI/dev/maintenance scripts.
#

code_lines = (
    stats["PROD_CODE"]["lines"]
    + stats["MIGRATIONS"]["lines"]
)

test_lines = stats["TESTS"]["lines"]

devrails_lines = stats["DEVRAILS"]["lines"]

all_text_lines = sum(
    category["lines"]
    for category in stats.values()
)

other_lines = (
    all_text_lines
    - code_lines
    - test_lines
    - devrails_lines
)


print()
print("=" * 46)
print("SUMMARY")
print("=" * 46)

print(f"{'CODE':12} {code_lines:>15,d} lines")
print(f"{'TESTS':12} {test_lines:>15,d} lines")
print(f"{'DEVRAILS':12} {devrails_lines:>15,d} lines")
print(f"{'OTHER':12} {other_lines:>15,d} lines")

print("-" * 46)
print(f"{'TOTAL':12} {all_text_lines:>15,d} lines")

print()

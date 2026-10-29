#!/usr/bin/env python3
"""Make the audited EvoTest client's base URL configurable, with an original backup."""

from __future__ import annotations

import argparse
import ast
import difflib
import hashlib
import os
from pathlib import Path
import stat
import sys
import tempfile


AUDITED_COMMIT = "f92474ce83c7aec69e45c30ccfaf2b69e66823de"
UPSTREAM_LF_SHA256 = "dc1708a194401403b1cd9c6c12d37d61b045cf12d59e15863d9349e0ec4686d6"
OLD = 'base_url="https://openrouter.ai/api/v1"'
NEW = 'base_url=os.getenv("LLM_BASE_URL", "https://openrouter.ai/api/v1")'


def digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--dry-run", action="store_true", help="Show the diff without writing anything")
    args = parser.parse_args()
    target = args.repo.expanduser().resolve() / "src/openai_helpers.py"
    backup = target.with_name(target.name + ".before_llm_base_url")
    temporary_name = None
    try:
        if target.is_symlink() or not target.is_file():
            raise ValueError("Expected a regular src/openai_helpers.py file")
        original = target.read_bytes()
        text = original.decode("utf-8").replace("\r\n", "\n")
        if text.count(NEW) == 1 and digest(text.replace(NEW, OLD, 1)) == UPSTREAM_LF_SHA256:
            print("Already patched: verified audited source plus this one replacement; no changes.")
            return 0
        if digest(text) != UPSTREAM_LF_SHA256 or text.count(OLD) != 1:
            raise ValueError(f"Unknown source structure; expected the audited file from {AUDITED_COMMIT}. No changes made.")
        updated_text = text.replace(OLD, NEW, 1)
        ast.parse(updated_text, filename=str(target))
        diff = "".join(difflib.unified_diff(text.splitlines(keepends=True),
                                          updated_text.splitlines(keepends=True),
                                          fromfile="a/src/openai_helpers.py",
                                          tofile="b/src/openai_helpers.py"))
        print(diff, end="")
        if args.dry_run:
            print("Dry run: no source or backup was written.")
            return 0
        if backup.is_symlink():
            raise ValueError("Backup path is a symlink; refusing to write")
        if backup.exists():
            if not backup.is_file() or backup.read_bytes() != original:
                raise ValueError("Existing backup differs; refusing to overwrite it")
        else:
            with backup.open("xb") as stream:
                stream.write(original)
            os.chmod(backup, stat.S_IMODE(target.stat().st_mode))
        updated_bytes = original.replace(OLD.encode("utf-8"), NEW.encode("utf-8"), 1)
        if updated_bytes.decode("utf-8").replace("\r\n", "\n") != updated_text:
            raise ValueError("Unexpected newline or replacement mismatch")
        mode = stat.S_IMODE(target.stat().st_mode)
        with tempfile.NamedTemporaryFile(mode="wb", prefix=".openai_helpers.patch-",
                                         dir=target.parent, delete=False) as stream:
            temporary_name = stream.name
            stream.write(updated_bytes)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary_name, mode)
        if target.read_bytes() != original:
            raise ValueError("Source changed during patching; refusing to replace it")
        os.replace(temporary_name, target)
        temporary_name = None
        print(f"Patched: {target}")
        print(f"Original backup: {backup}")
        print("Default endpoint remains OpenRouter; LLM_BASE_URL overrides it. No credentials were read.")
        return 0
    except (OSError, UnicodeError, ValueError, SyntaxError) as exc:
        print(f"Patch refused/failed: {exc}", file=sys.stderr)
        return 2
    finally:
        if temporary_name is not None:
            Path(temporary_name).unlink(missing_ok=True)


if __name__ == "__main__":
    raise SystemExit(main())

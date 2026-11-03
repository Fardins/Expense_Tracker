"""PreToolUse hook: block destructive actions on protected project files.

Reads the tool call JSON from stdin. Exit code 2 blocks the call and the
stderr message is shown to Claude. Any other exit lets the call through.
"""

import json
import re
import sys

# Paths that must never be deleted, moved, or overwritten.
PROTECTED = re.compile(
    r"(\.db\b|\.sqlite3?\b|(^|[\s/\"'=])\.env\b|\bmigrations\b|\bdatabase\b)",
    re.IGNORECASE,
)

# Shell / PowerShell / Python verbs that delete, move, or wipe files.
DESTRUCTIVE = re.compile(
    r"(\brm\b|\brmdir\b|\bunlink\b|\btruncate\b|\bshred\b"
    r"|\bdel\b|\berase\b|\brd\b|\bmv\b|\bmove\b"
    r"|remove-item|move-item|rename-item|clear-content|set-content|out-file"
    r"|\s-delete\b|git\s+clean"
    r"|os\.remove|os\.unlink|os\.rename|os\.replace|shutil\.rmtree|shutil\.move"
    r"|\.unlink\(|\.rename\(|\.write_text\(|\.write_bytes\()",
    re.IGNORECASE,
)

# Redirecting output straight into a protected file wipes it: `> foo.db`.
REDIRECT = re.compile(
    r">\s*[\"']?[^\s|;&]*(\.db|\.sqlite3?|\.env)\b", re.IGNORECASE
)

# Recursive delete of everything: `rm -rf *`, `rm -rf .`, `Remove-Item * -Recurse`.
WIPE_ALL = re.compile(
    r"(\brm\s+-\w*r\w*\s+(\*|\.|\./|\.\.)(\s|$)"
    r"|remove-item\s+(\*|\.)\s.*-recurse)",
    re.IGNORECASE,
)

# `git clean -x` deletes ignored files, which includes the database.
GIT_CLEAN_IGNORED = re.compile(r"git\s+clean\b.*\s-\w*x", re.IGNORECASE)

# Write/Edit may never touch these files directly.
PROTECTED_FILES = re.compile(r"(\.db|\.sqlite3?|(^|/)\.env)$", re.IGNORECASE)


def block(reason):
    print(f"BLOCKED by protect_files hook: {reason}", file=sys.stderr)
    sys.exit(2)


def check_command(cmd):
    normalized = cmd.replace("\\", "/")
    if REDIRECT.search(normalized):
        block("output redirect would overwrite a protected file")
    if WIPE_ALL.search(normalized):
        block("recursive delete of the whole directory")
    if GIT_CLEAN_IGNORED.search(normalized):
        block("git clean -x would delete ignored files like the database")
    if DESTRUCTIVE.search(normalized) and PROTECTED.search(normalized):
        block(
            "destructive command on a protected path "
            "(database / *.db / .env / migrations)"
        )


def check_file_path(path):
    if PROTECTED_FILES.search(path.replace("\\", "/")):
        block(f"cannot write or edit protected file: {path}")


def main():
    try:
        data = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return  # Malformed input: don't break every tool call.

    tool = data.get("tool_name", "")
    tool_input = data.get("tool_input", {}) or {}

    if tool in ("Bash", "PowerShell"):
        check_command(tool_input.get("command", ""))
    elif tool in ("Write", "Edit", "MultiEdit", "NotebookEdit"):
        check_file_path(
            tool_input.get("file_path") or tool_input.get("notebook_path") or ""
        )


if __name__ == "__main__":
    main()

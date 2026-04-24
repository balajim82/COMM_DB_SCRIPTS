#!/usr/bin/env python3
"""
helpers.py — Reads config/databases.yml and prints field values for shell scripts.

Commands:
  db-id           <config.yml>   Database id label used in logs
  git-repo        <config.yml>   Git repo URL
  git-branch      <config.yml>   Git branch (default: main)
  scripts-list    <config.yml>   Each schema name (scripts_path entry) on its own line
  subfolder-order <config.yml>   Each subfolder name on its own line
  history-schema  <config.yml>   Centralised history schema (default: flyway_history)
"""

import sys

if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, newline="\n")


def load_config(path: str) -> dict:
    try:
        import yaml
    except ImportError:
        raise SystemExit("PyYAML is required: pip install pyyaml") from None
    with open(path) as f:
        return yaml.safe_load(f) or {}


def main() -> None:
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)

    command     = sys.argv[1]
    config_path = sys.argv[2]
    cfg         = load_config(config_path)

    db = cfg.get("database")
    if not db:
        raise SystemExit("No 'database' key found in config. Check config/databases.yml.")

    if command == "db-id":
        print(db.get("id", "my_database"))

    elif command == "git-repo":
        val = db.get("git_repo", "")
        if not val:
            raise SystemExit("git_repo is not set in databases.yml")
        print(val)

    elif command == "git-branch":
        print(db.get("git_branch", "main"))

    elif command == "history-schema":
        print(db.get("history_schema", "flyway_history"))

    elif command == "scripts-list":
        paths = db.get("scripts_path", [])
        if isinstance(paths, str):
            # backward compat — single string treated as one schema
            print(paths)
        else:
            for p in paths:
                print(p)

    elif command == "subfolder-order":
        subfolders = db.get("subfolder_order", [])
        if not subfolders:
            raise SystemExit("subfolder_order is not defined in databases.yml")
        for s in subfolders:
            print(s)

    else:
        print(f"Unknown command: {command}", file=sys.stderr)
        print(__doc__, file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

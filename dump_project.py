import os

OUTPUT_FILE = "project_dump.txt"

# игнорируемые папки
IGNORE_DIRS = {
    "__pycache__", ".git", ".idea", ".vscode",
    "env", "venv", ".venv", "node_modules",
}

# игнорируемые расширения
IGNORE_EXT = {
    ".pyc", ".db", ".sqlite3", ".log",
    ".jpg", ".jpeg", ".png", ".gif",
    ".mp4", ".mp3", ".zip", ".tar", ".gz",
}


def should_ignore(path: str) -> bool:
    if any(part in IGNORE_DIRS for part in path.split(os.sep)):
        return True
    _, ext = os.path.splitext(path)
    return ext in IGNORE_EXT


def dump_file(path: str, output):
    output.write("\n\n" + "=" * 80 + "\n")
    output.write(f"FILE: {path}\n")
    output.write("=" * 80 + "\n\n")

    try:
        with open(path, "r", encoding="utf-8") as f:
            output.write(f.read())
    except Exception as e:
        output.write(f"[UNREADABLE FILE: {e}]")


def main():
    with open(OUTPUT_FILE, "w", encoding="utf-8") as output:
        for root, dirs, files in os.walk("."):
            dirs[:] = [d for d in dirs if d not in IGNORE_DIRS]

            for file in files:
                full_path = os.path.join(root, file)
                if should_ignore(full_path):
                    continue
                dump_file(full_path, output)

    print(f"Готово! Все файлы собраны в {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
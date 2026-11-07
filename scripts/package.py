"""Create a portable source + built UI archive, excluding state and dependencies."""
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "release" / "fault-tolerance-lab.zip"


def main():
    if not (ROOT / "frontend/dist/index.html").exists():
        raise SystemExit("Build the frontend before packaging")
    files = []
    for name in ("backend", "scripts", "tests", "docs", "frontend/src", "frontend/e2e", "frontend/dist", "frontend/public", "deploy", "design-system"):
        files.extend(path for path in (ROOT / name).rglob("*")
                     if path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc")
    for pattern in ("*.md", "*.bat", "requirements.txt", ".gitignore", "frontend/*.json",
                    "frontend/*.js", "frontend/*.ts", "frontend/*.html", ".env.example", "frontend/.env.example", "Dockerfile", "compose.yaml", ".dockerignore"):
        files.extend(ROOT.glob(pattern))
    OUTPUT.parent.mkdir(exist_ok=True)
    with ZipFile(OUTPUT, "w", ZIP_DEFLATED) as archive:
        for path in sorted(set(files)):
            archive.write(path, Path("fault-tolerance-lab") / path.relative_to(ROOT))
    print(f"Packaged {len(set(files))} files: {OUTPUT} ({OUTPUT.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()

#!/bin/zsh
set -eu
cd -- "$(dirname "$0")"
photo_python="${PHOTO_REVIEW_PYTHON:-$PWD/.venv/bin/python}"
if [[ ! -x "$photo_python" ]]; then photo_python="$(command -v python3 || true)"; fi
if [[ -z "$photo_python" ]] || ! "$photo_python" -c 'import sys; raise SystemExit(sys.version_info < (3, 11))'; then
  print '开发预览需要 Python 3.11 或更新版本。请按 README 安装 Python 和依赖。'
  read -r '?按回车退出…'
  exit 1
fi
photo_needs_dependencies=1
for photo_arg in "$@"; do
  case "$photo_arg" in
    --demo|--build-helper|--help|-h) photo_needs_dependencies=0 ;;
  esac
done
if (( photo_needs_dependencies )) && ! "$photo_python" -c 'import PIL' 2>/dev/null; then
  print '尚未安装开发依赖。请在此目录执行：'
  print 'python3 -m venv .venv'
  print '.venv/bin/python -m pip install -r requirements.txt'
  print '也可以运行 python3 launcher.py --demo，只查看合成演示。'
  read -r '?按回车退出…'
  exit 1
fi
exec "$photo_python" launcher.py "$@"

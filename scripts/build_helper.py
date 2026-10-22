"""Build an ad-hoc signed PhotoKit helper for this development checkout."""
import plistlib
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    if sys.platform != 'darwin':
        raise SystemExit('照片助手当前只支持 macOS。')
    if not shutil.which('xcrun') or not shutil.which('codesign'):
        raise SystemExit('请先安装 Xcode Command Line Tools，再重新构建。')
    app = ROOT / 'work/native/截图清理助手.app'
    binary = app / 'Contents/MacOS/PhotosTrash'
    binary.parent.mkdir(parents=True, exist_ok=True)
    info = {
        'CFBundleName': '截图清理助手',
        'CFBundleDisplayName': '照片整理器助手',
        'CFBundleIdentifier': 'org.photo-review.local-helper',
        'CFBundleExecutable': 'PhotosTrash',
        'CFBundlePackageType': 'APPL',
        'CFBundleVersion': '1',
        'CFBundleShortVersionString': '0.1.0',
        'LSUIElement': True,
        'NSPhotoLibraryUsageDescription': '读取系统照片图库，在你明确勾选并确认后将照片或视频移到最近删除。',
        'NSPhotoLibraryAddUsageDescription': '访问照片图库以完成你确认的照片与视频整理操作。',
    }
    with (app / 'Contents/Info.plist').open('wb') as stream:
        plistlib.dump(info, stream)
    subprocess.run(['xcrun', 'swiftc', '-O', str(ROOT / 'work/native/PhotosTrash.swift'),
                    '-framework', 'Photos', '-framework', 'AppKit', '-o', str(binary)], check=True)
    subprocess.run(['codesign', '--force', '--sign', '-', str(app)], check=True)
    subprocess.run(['codesign', '--verify', '--strict', str(app)], check=True)
    print(f'已构建开发助手：{app}\n这是本地临时签名，尚未公证；首次使用需手动授权完整照片访问。')


if __name__ == '__main__':
    main()

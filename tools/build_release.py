"""Build clean source archives and wheel using an explicit file allowlist.

Run from the source tree: python3 tools/build_release.py
Requires setuptools >=77 and wheel in the build environment; no network access.
"""
import hashlib
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
VERSION = '0.1.1'
TOP = f'IRdisC-{VERSION}'
FILES = ['irdisc.py', 'terminal_ui.py', 'irdisc_settings.py', 'chat_ux.py',
         'text_layout.py', 'release_ui.py', 'pyproject.toml', 'MANIFEST.in',
         'README.md', 'LICENSE', 'CHANGELOG.md', 'RELEASE_NOTES.md',
         'CONTRIBUTING.md', 'QA.md', '.gitignore']


def main():
    out = ROOT/'release'
    out.mkdir(exist_ok=True)
    paths = [ROOT/name for name in FILES]
    for directory, patterns in [('tests', ['*.py']), ('tools', ['*.py']),
                                ('assets', ['*.svg', '*.png', '*.md', '*.desktop'])]:
        for pattern in patterns:
            paths.extend(sorted((ROOT/directory).glob(pattern)))
    with tempfile.TemporaryDirectory() as temporary:
        source = Path(temporary)/TOP
        for path in paths:
            target = source/path.relative_to(ROOT)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, target)
        dist = out/'dist'
        dist.mkdir(exist_ok=True)
        subprocess.run([sys.executable, '-c',
                        'import setuptools.build_meta as b; b.build_wheel('+repr(str(dist))+')'],
                       cwd=source, check=True)
        # Archive only the allowlisted source files, never build output/config/logs.
        with zipfile.ZipFile(dist/f'{TOP}-source.zip', 'w', zipfile.ZIP_DEFLATED) as archive:
            for path in paths:
                archive.write(path, str(Path(TOP)/path.relative_to(ROOT)))
        with tarfile.open(dist/f'{TOP}-source.tar.gz', 'w:gz') as archive:
            for path in paths:
                archive.add(path, arcname=str(Path(TOP)/path.relative_to(ROOT)), recursive=False)
        artifacts = [dist/f'{TOP}-source.zip', dist/f'{TOP}-source.tar.gz',
                     dist/f'irdisc-{VERSION}-py3-none-any.whl']
        sums = ''.join(hashlib.sha256(p.read_bytes()).hexdigest()+'  '+p.name+'\n' for p in artifacts)
        (dist/'SHA256SUMS').write_text(sums)
        with zipfile.ZipFile(out/f'{TOP}-release.zip', 'w', zipfile.ZIP_DEFLATED) as archive:
            for path in paths:
                archive.write(path, str(Path(TOP)/path.relative_to(ROOT)))
            for path in artifacts+[dist/'SHA256SUMS']:
                archive.write(path, str(Path(TOP)/'dist'/path.name))
    print(out/f'{TOP}-release.zip')


if __name__ == '__main__':
    main()

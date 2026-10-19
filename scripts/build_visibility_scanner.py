"""Build the installable legacy Blender add-on ZIP using only the stdlib."""

import ast
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo


def build():
    root = Path(__file__).resolve().parents[1]
    source = root / 'addons' / 'orange_visibility_scanner' / '__init__.py'
    tree = ast.parse(source.read_text(encoding='utf-8'))
    info = next(ast.literal_eval(node.value) for node in tree.body
                if isinstance(node, ast.Assign)
                and any(isinstance(target, ast.Name) and target.id == 'bl_info' for target in node.targets))
    version = '.'.join(map(str, info['version']))
    destination = root / 'dist' / ('orange_visibility_scanner-' + version + '.zip')
    destination.parent.mkdir(exist_ok=True)
    member = ZipInfo('orange_visibility_scanner/__init__.py', date_time=(2026, 1, 1, 0, 0, 0))
    member.compress_type = ZIP_DEFLATED
    member.external_attr = 0o644 << 16
    with ZipFile(destination, 'w') as archive:
        archive.writestr(member, source.read_bytes())
    with ZipFile(destination) as archive:
        assert archive.namelist() == [member.filename]
        assert archive.read(member.filename) == source.read_bytes()
        assert archive.testzip() is None
    print(destination)
    return destination


if __name__ == '__main__':
    build()

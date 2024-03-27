# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['renderwatch_daemon.py'],
    pathex=[
        '.venv/lib/python3.10/site-packages',
    ],
    binaries=[],
    datas=[
        ('renderwatch/logging.yml', 'renderwatch'),
        ('renderwatch/actions.schema.yml', 'renderwatch'),
        ('config.templates/config.template.yml', 'config.templates'),
        ('config.templates/actions.template.yml', 'config.templates'),
        ('lib/yamale/VERSION', 'yamale'),
    ],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='renderwatch_daemon',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

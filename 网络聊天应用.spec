# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['client_gui.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('assets/login_background.png', 'assets'),
        ('assets/chat_background.png', 'assets'),
        ('assets/app_icon.png', 'assets'),
        ('app.ico', '.'),
    ],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='网络聊天应用',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['app.ico'],
)

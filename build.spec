# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec file for LLM File Translator
# Build command: pyinstaller build.spec
# NOTE: Must be built on Windows with Excel installed

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=[
        'xlwings',
        'pdfplumber',
        'fpdf',
        'PyQt5',
        'handlers.text_handler',
        'handlers.json_handler',
        'handlers.word_handler',
        'handlers.pptx_handler',
        'handlers.excel_handler',
        'handlers.pdf_handler',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    collect_all=['xlwings', 'PyQt5', 'pdfplumber', 'fpdf2'],
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='LLM_File_Translator',
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
)

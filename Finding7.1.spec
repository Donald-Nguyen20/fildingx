# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all

datas = []
binaries = []
hiddenimports = ['win32com.client', 'win32api', 'faiss', 'rapidfuzz', 'bs4', 'docx', 'pptx', 'fitz', 'sentence_transformers']
tmp_ret = collect_all('sentence_transformers')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('tokenizers')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]


a = Analysis(
    ['Finding7.1.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['matplotlib', 'pandas', 'tkinter', 'IPython', 'jupyter', 'notebook', 'pytest', 'cv2', 'flask', 'django', 'sqlalchemy', 'tensorflow', 'keras', 'cryptography', 'paramiko', 'tornado', 'lib2to3', 'xmlrpc', 'curses', 'pydoc_data', 'doctest', 'pygame', 'pyarrow', 'plotly', 'statsmodels', 'lightgbm', 'patsy', 'uvicorn', 'opentelemetry', 'datasets', 'mako', 'narwhals'],
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
    name='Finding7.1',
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
    icon=['icon.ico'],
)

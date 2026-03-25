# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['Finding7.1.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=['win32com.client', 'win32api', 'rapidfuzz', 'bs4', 'docx', 'pptx', 'fitz'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['matplotlib', 'pandas', 'tkinter', 'IPython', 'jupyter', 'notebook', 'pytest', 'cv2', 'flask', 'django', 'sqlalchemy', 'tensorflow', 'keras', 'cryptography', 'paramiko', 'tornado', 'lib2to3', 'xmlrpc', 'curses', 'pydoc_data', 'doctest', 'pygame', 'pyarrow', 'plotly', 'statsmodels', 'lightgbm', 'patsy', 'uvicorn', 'opentelemetry', 'datasets', 'mako', 'narwhals', 'torch', 'faiss', 'sentence_transformers', 'numpy', 'scipy', 'sklearn'],
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

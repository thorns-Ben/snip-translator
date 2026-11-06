# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller onedir build for JietuScreenshot."""

from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs


ROOT = Path(SPECPATH)

# RapidOCR's ONNX models are package data, not Python imports.
datas = collect_data_files("rapidocr_onnxruntime", include_py_files=False)
binaries = collect_dynamic_libs("onnxruntime")
# The DirectML wheel installs its provider DLLs into the shared onnxruntime
# package directory. collect_dynamic_libs includes those DLLs without copying
# source directories.

# The application imports its own package normally. No source directory or
# local configuration is copied; in particular llm_config.py is excluded.


a = Analysis(
    [str(ROOT / "run.py")],
    pathex=[str(ROOT)],
    binaries=binaries,
    datas=datas,
    hiddenimports=[
        "rapidocr_onnxruntime",
        "rapidocr_onnxruntime.main",
        "rapidocr_onnxruntime.utils.infer_engine",
        "onnxruntime.capi.onnxruntime_pybind11_state",
    ],
    excludes=["llm_config", "pynput"],
    noarchive=False,
)

pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="截图识字",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    name="截图识字",
)

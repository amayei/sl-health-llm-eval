# PyInstaller spec. Build from the repository root: pyinstaller packaging/workbench.spec
from pathlib import Path
root = Path(SPECPATH).parent
datas = [
    (str(root / "app" / "workbench" / "static"), "workbench/static"),
    (str(root / "data"), "data"),
    (str(root / "config"), "config"),
    (str(root / "results"), "results") if (root / "results").exists() else None,
]
datas = [d for d in datas if d]
a = Analysis([str(root / "app" / "main.py")], pathex=[str(root)], datas=datas,
             hiddenimports=["webview"], excludes=["matplotlib", "numpy", "tkinter"])
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="SL-Health-LLM-Eval-Workbench", console=False)
coll = COLLECT(exe, a.binaries, a.datas, name="SL-Health-LLM-Eval-Workbench")

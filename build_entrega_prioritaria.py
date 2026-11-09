from pathlib import Path
import zipfile
root=Path(".").resolve()
dist=root/"dist"; dist.mkdir(exist_ok=True)
out=dist/"ATRIO_ENTREGA_PRIORITARIA.pyz"
skip={".git",".github","tests","datos",".streamlit","__pycache__","dist"}
with zipfile.ZipFile(out,"w",zipfile.ZIP_DEFLATED,compresslevel=7) as z:
    z.write(root/"instalador_prioritario.py","__main__.py")
    for p in root.rglob("*"):
        if not p.is_file(): continue
        rel=p.relative_to(root)
        if any(part in skip for part in rel.parts): continue
        if p.suffix in {".pyc",".pyo"} or p.name in {".env","secrets.toml"}: continue
        z.write(p,"payload/"+rel.as_posix())
print(out, out.stat().st_size)

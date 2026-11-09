#!/usr/bin/env python3
"""Instalador seguro de la entrega prioritaria ATRIO. Conserva datos y recursos."""
from __future__ import annotations
import sys, zipfile, shutil, subprocess
from pathlib import Path
from datetime import datetime

def main():
    if len(sys.argv) < 2:
        print("Uso: python3 ATRIO_ENTREGA_PRIORITARIA.pyz RUTA_ATRIO [--comprobar]")
        return 2
    target = Path(sys.argv[1]).expanduser().resolve()
    check_only = "--comprobar" in sys.argv[2:]
    if not target.is_dir() or not (target / "app.py").is_file():
        print("ERROR: la ruta no es una instalación ATRIO existente con app.py. No se modificó nada.")
        return 2
    resources = target / "datos" / "recursos"
    if not resources.is_dir():
        print("ERROR: no se encontró datos/recursos. No se modificó nada.")
        return 2
    required = [
        resources / "PROGRAMACION DE CURSOS.xlsx",
        resources / "SISAE.zip",
        resources / "Plantilla_Datos_Docentes_PEA_CECATI31.xlsx",
        resources / "PEA_final en blanco.docx",
        resources / "acm" / "Formato_Presentacion.docx",
        resources / "acm" / "Formato_Vinculacion.docx",
        resources / "acm" / "Formato_Asignacion.docx",
    ]
    cred_candidates = [target / "FORMATO_CREDENCIALES.pptx", resources / "FORMATO_CREDENCIALES.pptx"]
    missing = [str(p.relative_to(target)) for p in required if not p.is_file()]
    if not any(p.is_file() for p in cred_candidates):
        missing.append("FORMATO_CREDENCIALES.pptx (junto a credenciales.py o en datos/recursos)")
    if missing:
        print("NO SE PUEDE INSTALAR: faltan recursos institucionales requeridos:")
        for item in missing: print(" - " + item)
        print("No se modificó ningún archivo.")
        return 3
    if check_only:
        print("COMPROBACIÓN CORRECTA: recursos PEA, ACM, SISAE y credenciales localizados.")
        return 0
    archive = Path(sys.argv[0])
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = target / "respaldos_codigo" / ("antes_entrega_prioritaria_" + stamp)
    with zipfile.ZipFile(archive, "r") as z:
        members = [n for n in z.namelist() if n.startswith("payload/") and not n.endswith("/")]
        if not members: raise RuntimeError("El paquete no contiene código ATRIO.")
        staged = target / ".atrio_entrega_prioritaria_tmp"
        if staged.exists(): shutil.rmtree(staged)
        staged.mkdir(parents=True)
        for name in members:
            rel = Path(name[len("payload/"):])
            if rel.is_absolute() or ".." in rel.parts or not rel.parts: raise RuntimeError("Ruta insegura: "+name)
            out = staged / rel
            out.parent.mkdir(parents=True, exist_ok=True)
            with z.open(name) as src, out.open("wb") as dst: shutil.copyfileobj(src, dst)
    files = [p for p in staged.rglob("*") if p.is_file() and p.name not in {".env","secrets.toml"}]
    try:
        for src in files:
            rel = src.relative_to(staged)
            if rel.parts[0] in {"datos",".streamlit",".git","tests",".github"}: continue
            dest = target / rel
            if dest.exists():
                saved = backup / rel
                saved.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(dest, saved)
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest)
        shutil.rmtree(staged, ignore_errors=True)
        req = target / "requirements.txt"
        if req.is_file():
            proc = subprocess.run([sys.executable,"-m","pip","install","-r",str(req)],text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
            if proc.returncode: raise RuntimeError("Falló la instalación de dependencias: "+proc.stdout[-4000:])
        print("INSTALACIÓN CORRECTA: ATRIO actualizado.")
        print("Respaldo del código anterior: "+str(backup))
        print("SQLite, Programación, SISAE, plantillas, recursos y documentos se conservaron.")
        print("Inicia con: cd "+str(target)+" && bash INICIAR.sh")
        return 0
    except Exception as exc:
        print("ERROR DURANTE LA INSTALACIÓN: "+str(exc))
        print("Respaldo disponible en: "+str(backup))
        print("No se eliminaron datos ni recursos.")
        return 5

if __name__ == "__main__":
    raise SystemExit(main())

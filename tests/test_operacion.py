import io,json,shutil,sys,zipfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import pytest
import centro as C
from docx import Document
from openpyxl import load_workbook

@pytest.fixture
def isolated(tmp_path,monkeypatch):
 original=C.RES
 for k,v in [('ROOT',tmp_path),('DATA',tmp_path/'datos'),('RES',tmp_path/'datos/recursos'),('OUT',tmp_path/'datos/salidas'),('ARCH',tmp_path/'datos/versiones')]:monkeypatch.setattr(C,k,v)
 shutil.copytree(original,C.RES)
 C.OUT.mkdir();C.ARCH.mkdir()
 C.import_program(C.RES/'PROGRAMACION DE CURSOS.xlsx')
 return C

def test_import_and_identity(isolated):
 before={g['fingerprint']:g['id'] for g in C.groups()}
 C.import_program(C.RES/'PROGRAMACION DE CURSOS.xlsx')
 assert before=={g['fingerprint']:g['id'] for g in C.groups()}
 assert len(before)==180
 assert sum(g['tipo']=='Repositorio' for g in C.groups())==8

def test_resource_validation_is_atomic(isolated):
 old=(C.RES/'DIAS_SIN_CLASE.json').read_bytes()
 with pytest.raises(ValueError):C.save_resource('DIAS_SIN_CLASE.json',b'["2026-99-99"]')
 assert (C.RES/'DIAS_SIN_CLASE.json').read_bytes()==old
 C.save_resource('DIAS_SIN_CLASE.json',b'["2026-11-16"]')
 assert len(list(C.ARCH.iterdir()))==1
 assert C.setting('calendario_confirmado') is False

def test_sisae(isolated):
 t=C.sisae_bytes((C.RES/'SISAE.zip').read_bytes())
 assert len(t['PROG_CURSOS1.DBF'])==52
 assert len(t['INSCRIPCION.DBF'])==433
 keys={g['CLAVE_CURS'] for g in t['PROG_CURSOS1.DBF']}
 assert all(r['CLV_CURSO'] in keys for r in t['INSCRIPCION.DBF'])

def test_status_and_backup(isolated):
 g=C.groups()[0];C.update_status(g['id'],'Revisado','Observado','Revisar temática')
 assert C.status(g['id'])['mce']=='Observado'
 z=zipfile.ZipFile(io.BytesIO(C.backup()))
 assert 'datos/atrio.sqlite3' in z.namelist()
 assert not any('key' in n.lower() for n in z.namelist())

def test_mce_export_regular_and_formula(isolated):
 g=next(g for g in C.groups() if g['tipo']=='Regular')
 out=C.mce_excel(g,{'Nombre del curso':'=HYPERLINK("x")','Duración':'60 HORAS'})
 w=load_workbook(io.BytesIO(out));assert w.active.max_column==20
 assert w.active['A2'].data_type!='f'
 assert C.status(g['id'])['mce']=='Sin verificar'

def test_generation_preconditions(isolated):
 g=next(g for g in C.groups() if g['tipo']=='Extensión')
 with pytest.raises(ValueError,match='calendario'):C.generate(g,10,academic={})
 regular=next(g for g in C.groups() if g['tipo']=='Regular')
 with pytest.raises(ValueError,match='solo para extensión'):C.generate(regular,10,academic={})

def test_real_word_pipeline_without_network(isolated):
 # Synthetic academic fixture for software QA, never an authorized course output.
 g=next(g for g in C.groups() if g['nombre']=='INFORMÁTICA BÁSICA' and g['duracion']==60)
 content=json.loads((C.RES/'PRUEBA_INFORMATICA_BASICA_v4.json').read_text())
 current=sum(u['mediacion_horas'] for u in content['unidades'])
 for u in content['unidades']:
  delta=u['mediacion_horas']*(1-8/current);u['mediacion_horas']-=delta;u['practica_horas']+=delta
 content['recursos']={
 'equipo':'10 computadoras con monitor, teclado y ratón para prácticas de informática por participante.',
 'herramientas':'1 sistema operativo y suite ofimática por equipo para ejercicios de archivos y documentos.',
 'materiales':'10 guías impresas de ejercicios y hojas para registrar procedimientos por participante.',
 'apoyo':'1 proyector para demostraciones y mobiliario con 10 mesas y sillas para prácticas del grupo.',
 'conectividad':'Conexión a Internet en los equipos para consultar ayuda y realizar prácticas de navegación supervisada.'}
 C.set_setting('calendario_confirmado',True)
 template_hash=C.sha((C.RES/'PEA_final en blanco.docx').read_bytes())
 out=C.generate(g,12,academic=content)
 assert out.exists();assert len(Document(out).tables)==28
 assert C.sha((C.RES/'PEA_final en blanco.docx').read_bytes())==template_hash
 assert C.status(g['id'])['doc']=='Generado'
 assert '12' in Document(out).tables[11].cell(0,0).text
 a=C.artifacts(g['id'])[0];C.mark_reviewed(a['id']);assert C.status(g['id'])['doc']=='Revisado'

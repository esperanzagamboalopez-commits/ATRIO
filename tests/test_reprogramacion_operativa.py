"""Pruebas aisladas del módulo de reprogramación operativa."""
import json
import sqlite3
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

from openpyxl import Workbook, load_workbook

import centro as C
import reprogramacion as R


class TestReprogramacion(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.resources = self.root / "recursos"
        self.archive = self.root / "versiones"
        self.resources.mkdir()
        self.archive.mkdir()
        self.excel = self.resources / "PROGRAMACION DE CURSOS.xlsx"
        wb = Workbook()
        ws = wb.active
        ws.title = "DOCENTE A"
        ws.cell(15, 2).value = "Curso de prueba"
        ws.cell(15, 5).value = date(2026, 11, 2)
        ws.cell(15, 6).value = date(2026, 11, 30)
        ws.cell(15, 7).value = 20
        wb.save(self.excel)
        wb.close()

        self.db_path = self.root / "atrio.sqlite3"
        db = sqlite3.connect(self.db_path)
        db.row_factory = sqlite3.Row
        db.executescript("""
            CREATE TABLE groups(id TEXT PRIMARY KEY,rowkey TEXT,fingerprint TEXT,payload TEXT,active INTEGER);
            CREATE TABLE events(id INTEGER PRIMARY KEY,at TEXT,group_id TEXT,action TEXT,payload TEXT);
            CREATE TABLE status(group_id TEXT PRIMARY KEY,doc TEXT,mce TEXT,note TEXT);
            CREATE TABLE artifacts(id TEXT PRIMARY KEY,group_id TEXT,created TEXT,path TEXT,content_path TEXT,fingerprint TEXT,reviewed INTEGER);
        """)
        self.payload = {
            "hoja": "DOCENTE A", "fila": 15, "nombre": "Curso de prueba",
            "tipo": "Extensión", "inicio": "2026-11-02", "fin": "2026-11-30",
            "duracion": 20.0, "horario": "LUNES A VIERNES 09:00 A 11:00",
            "poblacion": None, "aula": "", "especialidad_programada": "Informática",
            "_atrio": {"estado_programacion": "Vigente", "incluido_en_ultima_actualizacion": True},
        }
        self.fingerprint = C.fingerprint(self.payload)
        db.execute("INSERT INTO groups VALUES(?,?,?,?,1)", (
            "grupo-1", "DOCENTE A|15", self.fingerprint, json.dumps(self.payload, ensure_ascii=False)
        ))
        db.execute("INSERT INTO status VALUES(?,?,?,?)", ("grupo-1", "PEA elaborado", "Autorizado", "nota"))
        db.execute("INSERT INTO artifacts VALUES(?,?,?,?,?,?,?)", (
            "pea-1", "grupo-1", "2026-10-01", "pea.docx", "contenido.json", "fp-pea", 1
        ))
        db.commit()
        db.close()

        self.patchers = [
            patch.object(C, "RES", self.resources),
            patch.object(C, "ARCH", self.archive),
            patch.object(C, "connect", self._connect),
        ]
        for p in self.patchers:
            p.start()

    def tearDown(self):
        for p in reversed(self.patchers):
            p.stop()
        self.tmp.cleanup()

    def _connect(self):
        db = sqlite3.connect(self.db_path)
        db.row_factory = sqlite3.Row
        return db

    def _change(self):
        return {
            "id": "grupo-1", "fingerprint": self.fingerprint,
            "hoja": "DOCENTE A", "fila": 15, "curso": "Curso de prueba",
            "horas": 20.0, "inicio_anterior": "2026-11-02",
            "fin_anterior": "2026-11-30", "inicio_nuevo": "2026-11-02",
            "fin_nuevo": "2026-12-07", "horario": self.payload["horario"],
        }

    def test_aplica_excel_sqlite_y_conserva_identidad_y_expediente(self):
        backup, archivo = R._actualizar_excel_y_db([self._change()], self.excel)
        self.assertTrue(backup.is_file())
        self.assertTrue(archivo.is_file())
        wb = load_workbook(archivo, data_only=True)
        ws = wb["DOCENTE A"]
        self.assertEqual(ws.cell(15, 5).value.date(), date(2026, 11, 2))
        self.assertEqual(ws.cell(15, 6).value.date(), date(2026, 12, 7))
        self.assertEqual(ws.cell(15, 7).value, 20)
        wb.close()
        with self._connect() as db:
            row = db.execute("SELECT id,payload FROM groups").fetchone()
            self.assertEqual(row["id"], "grupo-1")
            self.assertEqual(json.loads(row["payload"])["fin"], "2026-12-07")
            status = db.execute("SELECT doc,mce,note FROM status WHERE group_id='grupo-1'").fetchone()
            self.assertEqual(tuple(status), ("PEA elaborado", "Autorizado", "nota"))
            self.assertEqual(db.execute("SELECT COUNT(*) FROM artifacts").fetchone()[0], 1)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM events WHERE action='Curso reprogramado'").fetchone()[0], 1)

    def test_revierte_excel_y_sqlite_si_falla_el_registro_de_eventos(self):
        before_excel = self.excel.read_bytes()
        with self._connect() as db:
            before_payload = db.execute("SELECT payload FROM groups WHERE id='grupo-1'").fetchone()[0]
            db.execute("""
                CREATE TRIGGER provocar_fallo_evento
                BEFORE INSERT ON events
                BEGIN SELECT RAISE(ABORT, 'fallo simulado de SQLite'); END;
            """)

        with self.assertRaisesRegex(sqlite3.IntegrityError, "fallo simulado"):
            R._actualizar_excel_y_db([self._change()], self.excel)

        self.assertEqual(self.excel.read_bytes(), before_excel)
        with self._connect() as db:
            after_payload = db.execute("SELECT payload FROM groups WHERE id='grupo-1'").fetchone()[0]
            self.assertEqual(after_payload, before_payload)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM events").fetchone()[0], 0)

    def test_no_modifica_excel_ni_sqlite_si_falla_reemplazo_de_archivo(self):
        before_excel = self.excel.read_bytes()
        with self._connect() as db:
            before_payload = db.execute("SELECT payload FROM groups WHERE id='grupo-1'").fetchone()[0]

        with patch.object(R.os, "replace", side_effect=OSError("fallo simulado de reemplazo")):
            with self.assertRaisesRegex(OSError, "fallo simulado"):
                R._actualizar_excel_y_db([self._change()], self.excel)

        self.assertEqual(self.excel.read_bytes(), before_excel)
        with self._connect() as db:
            after_payload = db.execute("SELECT payload FROM groups WHERE id='grupo-1'").fetchone()[0]
            self.assertEqual(after_payload, before_payload)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM events").fetchone()[0], 0)

    def test_recupera_excel_si_hubo_interrupcion_antes_del_commit_sqlite(self):
        original = self.excel.read_bytes()
        backup = self.archive / "backup_interrupcion.xlsx"
        backup.write_bytes(original)
        wb = load_workbook(self.excel)
        wb["DOCENTE A"].cell(15, 6).value = date(2027, 1, 15)
        wb.save(self.excel)
        wb.close()
        operation_id = "operacion-sin-commit"
        C._escribir_journal_programacion({
            "operation_id": operation_id, "excel": str(self.excel.resolve()),
            "backup": str(backup.resolve()), "created": C.now(),
        })

        self.assertTrue(C.recuperar_programacion())
        self.assertEqual(self.excel.read_bytes(), original)
        self.assertFalse(C._ruta_journal_programacion().exists())

    def test_conserva_excel_si_sqlite_ya_confirmo_antes_de_limpiar_journal(self):
        backup = self.archive / "backup_confirmado.xlsx"
        backup.write_bytes(self.excel.read_bytes())
        wb = load_workbook(self.excel)
        wb["DOCENTE A"].cell(15, 6).value = date(2027, 1, 15)
        wb.save(self.excel)
        wb.close()
        nuevo_excel = self.excel.read_bytes()
        operation_id = "operacion-confirmada"
        C._escribir_journal_programacion({
            "operation_id": operation_id, "excel": str(self.excel.resolve()),
            "backup": str(backup.resolve()), "created": C.now(),
        })
        with self._connect() as db:
            db.execute(
                "INSERT INTO events(at,group_id,action,payload) VALUES(?,?,?,?)",
                (C.now(), None, "Reprogramación aplicada",
                 json.dumps({"operation_id": operation_id})),
            )

        self.assertTrue(C.recuperar_programacion())
        self.assertEqual(self.excel.read_bytes(), nuevo_excel)
        self.assertFalse(C._ruta_journal_programacion().exists())

    def test_rechaza_huella_obsoleta_sin_modificar_excel(self):
        change = self._change()
        change["fingerprint"] = "huella-obsoleta"
        before = self.excel.read_bytes()
        with self.assertRaisesRegex(ValueError, "cambió"):
            R._actualizar_excel_y_db([change], self.excel)
        self.assertEqual(self.excel.read_bytes(), before)

    def test_no_incluye_grupos_pendientes_en_cascada(self):
        data = [
            dict(self.payload, id="grupo-1", fingerprint=self.fingerprint),
            dict(self.payload, id="pendiente", fingerprint="fp-p", inicio="2026-12-01",
                 fin="2026-12-20", _atrio={"estado_programacion": "Pendiente de reprogramación · no incluido en esta actualización", "incluido_en_ultima_actualizacion": False}),
        ]
        changes = R._planificar_cascada(data, "grupo-1", date(2026, 12, 7), [])
        self.assertEqual([x["id"] for x in changes], ["grupo-1"])

    def test_identifica_dias_y_carril_horario(self):
        self.assertEqual(R._parsear_dias("LUNES A VIERNES"), [0, 1, 2, 3, 4])
        self.assertEqual(R._clave_carril("LUNES A VIERNES 09:00 A 11:00"),
                         R._clave_carril("LUNES A VIERNES 09:00 A 11:00"))


if __name__ == "__main__":
    unittest.main(verbosity=2)

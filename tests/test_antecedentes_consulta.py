import json
import tempfile
import unittest
from pathlib import Path

import centro as C
import pea_biblioteca_109 as P109
import nucleo_atrio_101215 as N
import pea_wizard_112 as W


class TestAntecedentesConservados(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="atrio_antecedentes_")
        self.root = Path(self.tmp.name)
        self.old = {
            "ROOT": C.ROOT, "DATA": C.DATA, "OUT": C.OUT,
        }
        C.ROOT = self.root
        C.DATA = self.root / "datos"
        C.OUT = C.DATA / "salidas"
        C.DATA.mkdir(parents=True, exist_ok=True)
        C.OUT.mkdir(parents=True, exist_ok=True)

        payload = {
            "hoja": "DOCENTE DE PRUEBA",
            "fila": 15,
            "tipo": "Extensión",
            "nombre": "CURSO ANTERIOR DE PRUEBA",
            "inicio": "2026-11-01",
            "fin": "2026-12-01",
            "duracion": 60,
            "_atrio": {
                "estado_programacion":
                    "Sustituido por cambio de nombre · antecedente conservado"
            },
        }
        word = C.OUT / "pea_anterior" / "PEA_PARA_REVISION.docx"
        word.parent.mkdir(parents=True)
        word.write_bytes(b"contenido ficticio de prueba")

        db = C.connect()
        db.execute(
            "INSERT INTO groups(id,rowkey,fingerprint,payload,active) VALUES(?,?,?,?,0)",
            ("grupo-anterior", "DOCENTE DE PRUEBA|15", "fp-anterior",
             json.dumps(payload, ensure_ascii=False)),
        )
        db.execute(
            "INSERT INTO artifacts(id,group_id,created,path,content_path,fingerprint,reviewed) "
            "VALUES(?,?,?,?,?,?,1)",
            ("pea-anterior", "grupo-anterior", C.now(),
             str(word.relative_to(C.ROOT)), "", "fp-anterior"),
        )
        db.commit()
        db.close()

    def tearDown(self):
        C.ROOT = self.old["ROOT"]
        C.DATA = self.old["DATA"]
        C.OUT = self.old["OUT"]
        self.tmp.cleanup()

    def test_biblioteca_muestra_contexto_de_grupo_inactivo(self):
        rows = [
            row for row in P109.candidatos()
            if row.get("id") == "atrio:pea-anterior"
        ]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["curso"], "CURSO ANTERIOR DE PRUEBA")
        self.assertEqual(rows[0]["docente"], "DOCENTE DE PRUEBA")
        self.assertIn("antecedente conservado", P109._label(rows[0]))


    def test_marca_pea_del_mismo_grupo_con_huella_anterior(self):
        current_payload = {
            "hoja": "DOCENTE ACTUAL",
            "fila": 15,
            "tipo": "Extensión",
            "nombre": "CURSO CON MISMO NOMBRE",
            "inicio": "2026-11-15",
            "fin": "2026-12-15",
            "duracion": 72,
            "_atrio": {"estado_programacion": "Vigente"},
        }
        word = C.OUT / "pea_anterior" / "PEA_VERSION_ANTERIOR.docx"
        word.write_bytes(b"documento ficticio")
        db = C.connect()
        db.execute(
            "INSERT INTO groups(id,rowkey,fingerprint,payload,active) VALUES(?,?,?,?,1)",
            ("grupo-reprogramado", "DOCENTE ACTUAL|15", "fp-actual",
             json.dumps(current_payload, ensure_ascii=False)),
        )
        db.execute(
            "INSERT INTO artifacts(id,group_id,created,path,content_path,fingerprint,reviewed) "
            "VALUES(?,?,?,?,?,?,1)",
            ("pea-version-anterior", "grupo-reprogramado", C.now(),
             str(word.relative_to(C.ROOT)), "", "fp-anterior"),
        )
        db.commit()
        db.close()

        rows = [
            row for row in P109.candidatos()
            if row.get("id") == "atrio:pea-version-anterior"
        ]
        self.assertEqual(len(rows), 1)
        self.assertTrue(rows[0]["es_version_anterior"])
        self.assertIn("Versión anterior de programación", P109._label(rows[0]))
        current_group = {"id": "grupo-reprogramado", "fingerprint": "fp-actual"}
        previous = W._previous_artifacts(current_group)
        self.assertEqual([x["id"] for x in previous], ["pea-version-anterior"])

    def test_consulta_lectura_identifica_documento_del_antecedente(self):
        db = N.conectar(C.ROOT)
        try:
            report = N.conteo(db, detalle=True)
        finally:
            db.close()
        self.assertIn("CURSO ANTERIOR DE PRUEBA", report)
        self.assertIn("DOCENTE DE PRUEBA", report)
        self.assertIn("antecedente conservado", report)


if __name__ == "__main__":
    unittest.main(verbosity=2)

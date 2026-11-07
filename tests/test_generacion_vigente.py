"""Protecciones para evitar PEA generados desde una programación obsoleta."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import centro as C


class TestValidacionGrupoAntesDeGenerar(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.group = {"id": "g-1", "fingerprint": "fp-1", "nombre": "CURSO"}
        with patch.object(C, "DATA", Path(self.tmp.name)):
            with C.connect() as db:
                payload = {
                    "nombre": "CURSO",
                    "_atrio": {
                        "estado_programacion": "Vigente",
                        "incluido_en_ultima_actualizacion": True,
                    },
                }
                db.execute(
                    "INSERT INTO groups(id,rowkey,fingerprint,payload,active) VALUES(?,?,?,?,1)",
                    ("g-1", "docente|15", "fp-1", json.dumps(payload)),
                )

    def tearDown(self):
        self.tmp.cleanup()

    def test_acepta_la_misma_version_vigente(self):
        with patch.object(C, "DATA", Path(self.tmp.name)):
            self.assertTrue(C.validate_group_current(self.group))

    def test_rechaza_si_la_huella_cambio(self):
        with patch.object(C, "DATA", Path(self.tmp.name)):
            with C.connect() as db:
                db.execute("UPDATE groups SET fingerprint=? WHERE id=?", ("fp-2", "g-1"))
            with self.assertRaisesRegex(ValueError, "programación.*cambió"):
                C.validate_group_current(self.group)

    def test_rechaza_si_quedo_pendiente(self):
        with patch.object(C, "DATA", Path(self.tmp.name)):
            with C.connect() as db:
                row = db.execute("SELECT payload FROM groups WHERE id='g-1'").fetchone()
                payload = json.loads(row["payload"])
                payload["_atrio"] = {
                    "estado_programacion": "Pendiente de reprogramación",
                    "incluido_en_ultima_actualizacion": False,
                }
                db.execute("UPDATE groups SET payload=? WHERE id=?",
                           (json.dumps(payload), "g-1"))
            with self.assertRaisesRegex(ValueError, "pendiente de reprogramación"):
                C.validate_group_current(self.group)

    def test_rechaza_si_grupo_fue_desactivado(self):
        with patch.object(C, "DATA", Path(self.tmp.name)):
            with C.connect() as db:
                db.execute("UPDATE groups SET active=0 WHERE id='g-1'")
            with self.assertRaisesRegex(ValueError, "ya no está vigente"):
                C.validate_group_current(self.group)


if __name__ == "__main__":
    unittest.main(verbosity=2)

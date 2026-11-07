import unittest

from identidad_programacion import (
    grupo_incluido_en_actualizacion,
    grupos_operativos,
)


class TestSeparacionGruposOperativos(unittest.TestCase):
    def test_pendiente_se_conserva_pero_no_es_operativo(self):
        pendiente = {
            "id": "pendiente-1",
            "_atrio": {
                "estado_programacion": "Pendiente de reprogramación · no incluido en esta actualización",
                "incluido_en_ultima_actualizacion": False,
            },
        }
        self.assertFalse(grupo_incluido_en_actualizacion(pendiente))
        self.assertEqual(grupos_operativos([pendiente]), [])

    def test_grupo_incluido_sigue_en_procesos_operativos(self):
        vigente = {
            "id": "vigente-1",
            "_atrio": {
                "estado_programacion": "Vigente",
                "incluido_en_ultima_actualizacion": True,
            },
        }
        self.assertTrue(grupo_incluido_en_actualizacion(vigente))
        self.assertEqual(grupos_operativos([vigente]), [vigente])

    def test_grupo_antiguo_sin_metadata_mantiene_compatibilidad(self):
        antiguo = {"id": "antiguo-1"}
        self.assertTrue(grupo_incluido_en_actualizacion(antiguo))
        self.assertEqual(grupos_operativos([antiguo]), [antiguo])

    def test_sustituido_no_se_incluye_en_operacion(self):
        sustituido = {
            "id": "sustituido-1",
            "_atrio": {
                "estado_programacion": "Sustituido por cambio de nombre · antecedente conservado",
                "incluido_en_ultima_actualizacion": False,
            },
        }
        self.assertFalse(grupo_incluido_en_actualizacion(sustituido))
        self.assertEqual(grupos_operativos([sustituido]), [])

    def test_filtro_no_modifica_ni_elimina_registros_originales(self):
        pendiente = {
            "id": "pendiente-2",
            "_atrio": {
                "estado_programacion": "Pendiente de reprogramación",
                "incluido_en_ultima_actualizacion": False,
            },
        }
        vigente = {"id": "vigente-2", "_atrio": {"incluido_en_ultima_actualizacion": True}}
        original = [pendiente, vigente]
        resultado = grupos_operativos(original)
        self.assertEqual(len(original), 2)
        self.assertEqual([x["id"] for x in resultado], ["vigente-2"])


if __name__ == "__main__":
    unittest.main()

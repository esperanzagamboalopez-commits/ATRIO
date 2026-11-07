import unittest

from identidad_programacion import planificar_conciliacion


def group(
    name="MANTENIMIENTO",
    teacher="DOCENTE A",
    specialty="ELECTRICIDAD",
    kind="Extensión",
    start="2026-11-01",
    end="2026-12-01",
    hours=60,
    schedule="LUNES A VIERNES 08:00-12:00",
    row=15,
    fp="fp",
):
    return {
        "hoja": teacher, "fila": row, "nombre": name, "tipo": kind,
        "especialidad_programada": specialty, "inicio": start, "fin": end,
        "duracion": hours, "horario": schedule, "poblacion": 10,
        "aula": "T1", "rowkey": f"{teacher}|{row}", "fingerprint": fp,
    }


def prior(uid, item):
    return {
        "id": uid, "rowkey": item["rowkey"],
        "fingerprint": item["fingerprint"], "payload": item,
    }


class TestConciliacionProgramacion(unittest.TestCase):
    def test_cambio_docente_conserva_identidad_y_reutiliza_base(self):
        old = group(fp="old-fp")
        new = group(
            teacher="DOCENTE B", fp="new-fp", start="2026-11-05",
            end="2026-12-05", hours=72,
            schedule="MARTES A SABADO 09:00-13:00",
        )
        plan = planificar_conciliacion([prior("g-1", old)], [new])
        match = plan["vinculados"][0]
        self.assertEqual(match["id"], "g-1")
        self.assertTrue(match["docente_cambio"])
        self.assertEqual(
            match["accion_pea"],
            "reutilizar_base_y_revisar_docente_y_horas",
        )
        self.assertFalse(plan["nuevos"])

    def test_cambio_nombre_exige_pea_nuevo_y_conserva_antecedente(self):
        old = group(fp="old-fp")
        new = group(name="INSTALACIONES ELECTRICAS INDUSTRIALES", fp="new-fp")
        plan = planificar_conciliacion([prior("g-1", old)], [new])
        self.assertTrue(plan["nuevos"][0]["requiere_pea_nuevo"])
        self.assertEqual(plan["nuevos"][0]["posible_grupo_anterior"], "g-1")
        self.assertEqual(plan["no_incluidos"][0]["id"], "g-1")
        self.assertFalse(plan["no_incluidos"][0]["eliminar"])

    def test_cascada_de_ocho_de_diez_conserva_los_dos_no_alcanzados(self):
        old = [
            prior(f"g-{i}", group(name=f"CURSO {i}", row=14+i, fp=f"fp-{i}"))
            for i in range(10)
        ]
        incoming = [
            group(name=f"CURSO {i}", row=14+i, fp=f"fp-{i}")
            for i in range(8)
        ]
        plan = planificar_conciliacion(old, incoming)
        self.assertEqual(
            plan["resumen"],
            {"recibidos": 8, "vinculados": 8, "nuevos": 0, "no_incluidos": 2},
        )
        self.assertEqual(
            {item["id"] for item in plan["no_incluidos"]}, {"g-8", "g-9"}
        )
        self.assertTrue(all(not item["eliminar"] for item in plan["no_incluidos"]))

    def test_cambio_horas_conserva_identidad_y_pide_ajuste(self):
        old = group(fp="old-fp", hours=60)
        new = group(
            fp="new-fp", hours=72,
            start="2026-11-03", end="2026-12-03",
        )
        plan = planificar_conciliacion([prior("g-1", old)], [new])
        match = plan["vinculados"][0]
        self.assertEqual(match["id"], "g-1")
        self.assertTrue(match["horas_cambiaron"])
        self.assertEqual(
            match["accion_pea"], "reajustar_horas_y_revisar_contenido"
        )

    def test_candidatos_duplicados_requieren_revision_no_adivina(self):
        a = group(teacher="DOCENTE A", row=15, fp="old-a")
        b = group(teacher="DOCENTE B", row=16, fp="old-b")
        new = group(teacher="DOCENTE C", row=20, fp="new")
        plan = planificar_conciliacion(
            [prior("g-a", a), prior("g-b", b)], [new]
        )
        self.assertTrue(plan["nuevos"][0]["requiere_revision_manual"])
        self.assertFalse(plan["nuevos"][0]["requiere_pea_nuevo"])
        self.assertEqual(len(plan["no_incluidos"]), 2)

    def test_curso_nuevo_exige_pea(self):
        new = group(name="CURSO COMPLETAMENTE NUEVO", fp="new-fp")
        plan = planificar_conciliacion([], [new])
        self.assertEqual(plan["nuevos"][0]["motivo"], "curso_nuevo")
        self.assertTrue(plan["nuevos"][0]["requiere_pea_nuevo"])


if __name__ == "__main__":
    unittest.main(verbosity=2)

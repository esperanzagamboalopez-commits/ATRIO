"""Procedencia explícita: no inventa fechas de corte o periodos."""
from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

@dataclass(frozen=True)
class Procedencia:
    fuente: str
    fecha_consulta: str
    corte: str
    periodo: str
    unidad: str
    estado: str = 'verificado'

    def pie(self):
        return (f'**Procedencia:** {self.fuente} · Consulta: {self.fecha_consulta} · '
                f'Corte: {self.corte} · Periodo/alcance: {self.periodo} · '
                f'Unidad: {self.unidad} · Estado: {self.estado}.')


def fecha_consulta():
    return datetime.now(ZoneInfo('America/Mexico_City')).strftime('%Y-%m-%d %H:%M')


def anotar(texto, *, fuente, unidad, periodo='sin filtro temporal', corte='no aplica', estado='verificado'):
    pr = Procedencia(fuente=fuente, fecha_consulta=fecha_consulta(), corte=corte,
                     periodo=periodo, unidad=unidad, estado=estado)
    return f'{texto}\n\n{pr.pie()}'

"""ATRIO: revisión segura de la estructura de SISAE.zip.
No extrae archivos, no imprime registros ni valores personales.
Solo muestra tablas DBF, conteos declarados y nombres/tipos de campos.
"""
from pathlib import Path
from zipfile import ZipFile, BadZipFile
import argparse
import struct


def examinar(ruta):
    ruta = Path(ruta).expanduser()
    if not ruta.is_file():
        print('No se encontró el corte SISAE.zip en:', ruta)
        return 1
    try:
        with ZipFile(ruta) as z:
            dbfs = sorted((i for i in z.infolist() if not i.is_dir()
                           and Path(i.filename).suffix.lower() == '.dbf'),
                          key=lambda i: i.filename.lower())
            print(f'Tablas DBF encontradas: {len(dbfs)}')
            if not dbfs:
                print('El ZIP no contiene tablas DBF identificables.')
            for info in dbfs[:120]:
                print('\nTABLA:', Path(info.filename).name)
                if info.file_size > 120 * 1024 * 1024:
                    print('  Encabezado omitido por tamaño declarado excesivo.')
                    continue
                try:
                    with z.open(info) as f:
                        h = f.read(32)
                        if len(h) != 32:
                            print('  Encabezado insuficiente.'); continue
                        n = struct.unpack_from('<I', h, 4)[0]
                        header_len = struct.unpack_from('<H', h, 8)[0]
                        rec_len = struct.unpack_from('<H', h, 10)[0]
                        if not 33 <= header_len <= 65535:
                            print('  Cabecera DBF no reconocida.'); continue
                        descriptor = f.read(header_len - 32)
                        print(f'  Filas declaradas en encabezado: {n} (no equivale a inscritos vigentes)')
                        print(f'  Longitud de registro: {rec_len}')
                        fields = []
                        for x in range(0, min(len(descriptor), 32 * 250), 32):
                            chunk=descriptor[x:x+32]
                            if len(chunk)<32 or chunk[0]==0x0d: break
                            name=chunk[:11].split(b'\0')[0].decode('latin-1','replace').strip()
                            if not name: continue
                            typ=chr(chunk[11]) if 32 <= chunk[11] <= 126 else '?'
                            fields.append(f'{name}({typ})')
                        print('  Columnas:', ', '.join(fields) if fields else 'No identificadas')
                except (OSError, RuntimeError, ValueError, struct.error) as e:
                    print('  No se pudo leer cabecera:', type(e).__name__)
            if len(dbfs)>120:
                print(f'... Se omitieron {len(dbfs)-120} tablas adicionales.')
        return 0
    except (BadZipFile,OSError) as e:
        print('Error al abrir SISAE.zip:', type(e).__name__)
        return 1


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('ruta',help='Ruta de SISAE.zip, p. ej. datos/recursos/SISAE.zip')
    args=parser.parse_args()
    raise SystemExit(examinar(args.ruta))

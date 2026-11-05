from pathlib import Path
p = Path('interfaz.py')
code = p.read_text(encoding='utf-8')

inyeccion = '''
    # --- TARJETA MCE GLOBAL ---
    import centro as C
    total_mce = len(data)
    subidos = sum(1 for g in data if C.status(g['id'])['mce'] not in ('No subido', 'Sin verificar', 'Observado', ''))
    pct = int((subidos / total_mce) * 100) if total_mce > 0 else 0
    mce_html = f"""
    <div style="background: #fffdfa; border: 1px solid #dfd1c8; border-radius: 12px; padding: 18px; margin-bottom: 20px; box-shadow: 0 2px 8px #26162108;">
        <div style="display: flex; justify-content: space-between; font-size: 13px; font-weight: 700; color: #252022; margin-bottom: 12px;">
            <span>MCE Global (Avance del Ciclo)</span>
            <span>{total_mce} cursos totales en ATRIO</span>
        </div>
        <div style="height: 10px; background: #e0d6d0; border-radius: 5px; overflow: hidden; margin-bottom: 10px;">
            <div style="height: 100%; width: {pct}%; background: #8d405e; border-radius: 5px;"></div>
        </div>
        <div style="display: flex; justify-content: space-between; font-size: 11px; color: #695762;">
            <span>Subidos al MCE: {subidos}</span>
            <span>Faltantes: {total_mce - subidos}</span>
            <span>{pct}% del total</span>
        </div>
    </div>
    """
    text = text.replace('El avance de tu ciclo', mce_html + 'El avance de tu ciclo')
'''

old_return = "for key,value in replacements.items():text=text.replace(key,value)\n    return text"
new_return = "for key,value in replacements.items():text=text.replace(key,value)\n" + inyeccion + "\n    return text"

if old_return in code:
    code = code.replace(old_return, new_return)
    p.write_text(code, encoding='utf-8')
    print('✅ Inyección exitosa. La tarjeta ya está dentro de inicio.html.')
else:
    print('❌ No se encontró el punto exacto en interfaz.py')

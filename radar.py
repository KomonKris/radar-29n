"""Radar 29N: evolutivo, mensajes y envío a Telegram.

La extracción la hace Claude en la rutina: lee el PDF de Onclusive (texto vía
`pdftext`) y el DOCX/XLSX de Maldita y escribe `hoy.json` con el esquema de
SCHEMA.md. Este script hace lo determinista:

  python radar.py pdftext <onclusive.pdf>                 texto del PDF (PyMuPDF)
  python radar.py validar <hoy.json>                      sale 1 si no cuadra
  python radar.py evolutivo <hoy.json> <anterior.json|->  añade "evolutivo" a hoy.json
  python radar.py mensaje <hoy.json> ecosistema|donantes  texto HTML de Telegram
  python radar.py informe <hoy.json>                      HTML del PDF de donantes
  python radar.py enviar <destino> --texto F [--pdf F]    destino: donantes|ecosistema|aviso
  python radar.py --self-check

`enviar` respeta config.json: con "ensayo": true todo va a aviso_chat_id.
Token en la variable de entorno TELEGRAM_BOT_TOKEN.
"""
import argparse
import html
import json
import os
import sys
import urllib.parse
import urllib.request
import uuid
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent
TEMAS = ["Vivienda", "Bulos y desinformación", "Voto exterior", "Voto por correo",
         "Clima", "Energía", "Primer voto joven"]
BLOQUES = ("redes", "digitales", "analogico")
MINIMO = {"redes": 10, "digitales": 10, "analogico": 2}  # menciones/piezas para que el bloque cuente
PIE = "Análisis descriptivo de la conversación pública; no constituye posicionamiento."
MESES = "enero febrero marzo abril mayo junio julio agosto septiembre octubre noviembre diciembre".split()
ELECCIONES = date(2026, 11, 29)


def cargar(p):
    return json.loads(Path(p).read_text(encoding="utf8"))


def config():
    return cargar(ROOT / "config.json")


# --- validación -----------------------------------------------------------

def errores(d):
    e = []
    vol = d.get("volumen", {})
    for b in BLOQUES:
        if not isinstance(vol.get(b), (int, float)) or vol[b] <= 0:
            e.append(f"volumen.{b} falta o no es positivo")
    for t, v in d.get("temas", {}).items():
        for b in ("redes", "digitales"):
            x = v.get(b)
            if x is not None and not 0 <= x <= 100:
                e.append(f"temas.{t}.{b}={x} fuera de 0-100")
        a = v.get("analogico")
        if a is not None and vol.get("analogico") and not 0 <= a <= vol["analogico"]:
            e.append(f"temas.{t}.analogico={a} mayor que el total analógico")
    faltan = [t for t in TEMAS if t not in d.get("temas", {})]
    if faltan:
        e.append("faltan temas prioritarios: " + ", ".join(faltan))
    for n, x in d.get("narrativas_redes", {}).items():
        if not 0 <= x <= 100:
            e.append(f"narrativas_redes.{n}={x} fuera de 0-100")
    if len(d.get("hallazgos", [])) == 0:
        e.append("sin hallazgos")
    return e


# --- evolutivo ------------------------------------------------------------

def escala(delta):
    """Δ relativo de cuota -> -2..+2 (umbrales del diseño)."""
    if delta >= 0.50:
        return 2
    if delta >= 0.25:
        return 1
    if delta > -0.20:
        return 0
    if delta > -0.50:
        return -1
    return -2


def cuotas(d, tema):
    """Cuota (%) y nº absoluto por bloque de un tema prioritario."""
    v, vol = d["temas"].get(tema, {}), d["volumen"]
    out = {}
    for b in ("redes", "digitales"):
        if v.get(b) is not None:
            out[b] = (v[b], v[b] * vol[b] / 100)
    if v.get("analogico") is not None:
        out["analogico"] = (100 * v["analogico"] / vol["analogico"], v["analogico"])
    return out


def nota(hoy, ant):
    """hoy/ant: {bloque: (cuota, n)}. Devuelve nota -2..2, o None si poco dato."""
    notas = []
    for b, (c, n) in hoy.items():
        if b not in ant:
            continue
        c0, n0 = ant[b]
        if max(n, n0) < MINIMO[b]:
            continue
        if c0 == 0:
            notas.append(2 if c > 0 else 0)
        else:
            notas.append(escala(round((c - c0) / c0, 6)))  # 0,2→0,3 da 0,4999… sin redondear
    if not notas:
        return None
    m = sum(notas) / len(notas)
    # ponytail: ±0,5 (bloques en direcciones opuestas) redondea a 0, hacia cero
    return int(abs(m) + 0.5 - 1e-9) * (1 if m >= 0 else -1)


def evolutivo(hoy, ant):
    filas = []
    for t in TEMAS:
        if ant is None:
            filas.append({"tema": t, "nota": None, "estado": "base"})
            continue
        n = nota(cuotas(hoy, t), cuotas(ant, t))
        filas.append({"tema": t, "nota": n, "estado": "poco dato" if n is None else "medido"})
    nh, na = hoy.get("narrativas_redes", {}), (ant or {}).get("narrativas_redes", {})
    vr, vr0 = hoy["volumen"]["redes"], (ant or {}).get("volumen", {}).get("redes", 0)
    if ant is not None:
        for n in nh:
            if n in TEMAS:
                continue
            if n in na:
                x = nota({"redes": (nh[n], nh[n] * vr / 100)}, {"redes": (na[n], na[n] * vr0 / 100)})
                filas.append({"tema": n, "nota": x, "estado": "poco dato" if x is None else "medido", "narrativa": True})
            else:
                filas.append({"tema": n, "nota": None, "estado": "NUEVA", "narrativa": True})
        for n in na:
            if n not in nh and n not in TEMAS:
                filas.append({"tema": n, "nota": None, "estado": "DESAPARECE", "narrativa": True})
    return {"comparado_con": (ant or {}).get("fecha"), "filas": filas}


def indicador(f):
    if f["nota"] is None:
        return {"base": "base", "poco dato": "poco dato"}.get(f["estado"], f["estado"])
    s = "▲" if f["nota"] > 0 else "▼" if f["nota"] < 0 else "●"
    return f"{f['nota']:+d} {s}" if f["nota"] else f"0 {s}"


# --- textos ---------------------------------------------------------------

def fecha_larga(iso):
    d = date.fromisoformat(iso)
    return f"{d.day} de {MESES[d.month - 1]}"


def e(s):
    return html.escape(str(s), quote=False)


def mensaje(d, para):
    ev = {f["tema"]: f for f in d.get("evolutivo", {}).get("filas", [])}
    falta = d.get("pendiente", [])
    L = [f"<b>Radar 29N · {fecha_larga(d['fecha'])}</b> · faltan {(ELECCIONES - date.fromisoformat(d['fecha'])).days} días"]
    if falta:
        L.append(f"<i>{e(', '.join(falta))}: pendiente, se completará mañana.</i>")
    if d.get("tono"):
        L += ["", e(d["tono"])]
    if d.get("hallazgos"):
        L += ["", "<b>Cinco hallazgos</b>"]
        L += [f"{i}. {e(h['texto'])}" for i, h in enumerate(d["hallazgos"][:5], 1)]
    t = d.get("traccion")
    if t:
        L += ["", f"<b>Más tracción:</b> {e(t)}" + (f" ({indicador(ev[t])})" if t in ev else "")]
    if d.get("marcos"):
        L += ["", "<b>Marcos</b>"]
        for m in d["marcos"]:
            x = f"<b>{e(m['tema'])}</b>: {e(m['dominante'])}"
            if m.get("bloques"):
                x += " — " + e(m["bloques"])
            L.append(x)
    if para == "donantes" and d.get("maldita"):
        L += ["", f"<b>Desinformación (Maldita):</b> {e(d['maldita']['resumen'])}"]
    if d.get("vigilar"):
        L += ["", "<b>A vigilar</b>"]
        L += [f"· {e(v['fecha'] + ' · ') if v.get('fecha') else ''}{e(v['texto'])}" for v in d["vigilar"][:2]]
    L += ["", f"<i>{PIE}</i>"]
    return "\n".join(L)


def informe(d):
    ev = d.get("evolutivo", {})
    css = ("body{font-family:Arial,sans-serif;font-size:10.5pt;color:#111}h1{font-size:16pt;margin:0}"
           "h2{font-size:12pt;margin:14pt 0 4pt;border-bottom:1px solid #999}table{border-collapse:collapse;width:100%}"
           "td,th{border:1px solid #bbb;padding:3pt 5pt;text-align:left;vertical-align:top}th{background:#eee}"
           ".pie{font-size:8.5pt;color:#555;margin-top:16pt}")
    v = d["volumen"]
    H = [f"<html><head><meta charset='utf-8'><style>{css}</style></head><body>",
         f"<h1>Radar 29N · {e(fecha_larga(d['fecha']))} de {d['fecha'][:4]}</h1>",
         f"<p>{(ELECCIONES - date.fromisoformat(d['fecha'])).days} días para las elecciones del 29N · "
         f"{v['redes']:,} menciones en redes · {v['digitales']:,} piezas digitales · {v['analogico']} piezas analógicas</p>".replace(",", ".")]
    if d.get("pendiente"):
        H.append(f"<p><i>{e(', '.join(d['pendiente']))}: pendiente, se completará mañana.</i></p>")
    if d.get("tono"):
        H.append(f"<p>{e(d['tono'])}</p>")
    H.append("<h2>1. De qué se habla: cinco hallazgos</h2><ol>")
    H += [f"<li>{e(h['texto'])}</li>" for h in d.get("hallazgos", [])[:5]]
    H.append("</ol>")
    H.append("<h2>2. Qué ha cambiado: evolutivo</h2>")
    if ev.get("comparado_con"):
        H.append(f"<p>Frente al informe del {e(fecha_larga(ev['comparado_con']))}. "
                 "Variación de cuota por bloque: ≥+50% → +2 · +25..50% → +1 · −20..+25% → 0 · −50..−20% → −1 · ≤−50% → −2.</p>")
    else:
        H.append("<p>Primer informe: línea base, sin variación.</p>")
    H.append("<table><tr><th>Tema</th><th>Redes %</th><th>Digitales %</th><th>Analógico</th><th>Evolutivo</th></tr>")
    for f in ev.get("filas", []):
        t = d["temas"].get(f["tema"], {})
        r = d.get("narrativas_redes", {}).get(f["tema"]) if f.get("narrativa") else t.get("redes")
        cel = lambda x: "—" if x is None else e(x)
        H.append(f"<tr><td>{e(f['tema'])}{' (narrativa)' if f.get('narrativa') else ''}</td><td>{cel(r)}</td>"
                 f"<td>{cel(t.get('digitales'))}</td><td>{cel(t.get('analogico'))}</td><td>{e(indicador(f))}</td></tr>")
    H.append("</table>")
    if d.get("marcos"):
        H.append("<h2>3. Qué evidencia lo sostiene: marcos por tema</h2><table><tr><th>Tema</th><th>Marco dominante</th><th>Qué dice cada bloque</th><th>Fuente</th></tr>")
        H += [f"<tr><td>{e(m['tema'])}</td><td>{e(m['dominante'])}</td><td>{e(m.get('bloques', ''))}</td><td>{e(m.get('fuente', ''))}</td></tr>" for m in d["marcos"]]
        H.append("</table>")
    if d.get("clima"):
        H.append(f"<h2>4. Clima y energía</h2><p>{e(d['clima'])}</p>")
    m = d.get("maldita")
    if m:
        H.append(f"<h2>5. Desinformación</h2><p>{e(m['resumen'])}</p><ul>")
        H += [f"<li>{e(n)}</li>" for n in m.get("narrativas", [])]
        H.append("</ul>")
        if m.get("claims"):
            H.append("<p>Claims del día:</p><ul>")
            for c in m["claims"]:
                link = f" · <a href='{e(c['verificacion'])}'>verificación</a>" if c.get("verificacion") else ""
                H.append(f"<li>{e(c['texto'])}{link}</li>")
            H.append("</ul>")
        H.append("<p><i>Fuente: Fundación Maldita.es</i></p>")
    if d.get("vigilar"):
        H.append("<h2>6. A vigilar</h2><ul>")
        H += [f"<li>{e(v['fecha'] + ' · ') if v.get('fecha') else ''}{e(v['texto'])}</li>" for v in d["vigilar"]]
        H.append("</ul>")
    H.append(f"<h2>Nota metodológica</h2><p>{e(d.get('metodologia', ''))}</p>")
    H.append(f"<p class='pie'>{PIE}</p></body></html>")
    return "\n".join(H)


# --- telegram -------------------------------------------------------------

def destino_chat(destino, cfg):
    tg = cfg["telegram"]
    if cfg.get("ensayo") or destino == "aviso":
        return tg["aviso_chat_id"], None
    if destino == "donantes":
        return tg["donantes_chat_id"], None
    if destino == "ecosistema":
        if not tg.get("ecosistema_chat_id"):
            sys.exit("[error] ecosistema_chat_id vacío en config.json")
        return tg["ecosistema_chat_id"], tg.get("ecosistema_thread_id")
    sys.exit(f"[error] destino desconocido: {destino}")


def tg_call(metodo, campos, archivo=None):
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        sys.exit("[error] falta TELEGRAM_BOT_TOKEN")
    url = f"https://api.telegram.org/bot{token}/{metodo}"
    if archivo:
        b = uuid.uuid4().hex
        partes = []
        for k, v in campos.items():
            partes.append(f'--{b}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode())
        partes.append(f'--{b}\r\nContent-Disposition: form-data; name="document"; filename="{Path(archivo).name}"\r\n'
                      f"Content-Type: application/pdf\r\n\r\n".encode() + Path(archivo).read_bytes() + b"\r\n")
        partes.append(f"--{b}--\r\n".encode())
        req = urllib.request.Request(url, b"".join(partes), {"Content-Type": f"multipart/form-data; boundary={b}"})
    else:
        req = urllib.request.Request(url, urllib.parse.urlencode(campos).encode())
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            res = json.load(r)
    except urllib.error.HTTPError as ex:  # no imprimir la URL: lleva el token
        res = json.load(ex)
    if not res.get("ok"):
        sys.exit(f"[error] Telegram {metodo}: {res.get('description')}")
    return res


def enviar(destino, texto, pdf=None):
    cfg = config()
    chat, hilo = destino_chat(destino, cfg)
    if cfg.get("ensayo") and destino != "aviso":
        texto = f"<b>[ENSAYO → {destino}]</b>\n" + texto
    base = {"chat_id": chat, "parse_mode": "HTML"}
    if hilo:
        base["message_thread_id"] = hilo
    if pdf:
        # caption máx. 1024: el texto va aparte y el PDF justo después
        tg_call("sendMessage", {**base, "text": texto, "disable_web_page_preview": "true"})
        tg_call("sendDocument", {k: v for k, v in base.items() if k != "parse_mode"}, pdf)
    else:
        tg_call("sendMessage", {**base, "text": texto, "disable_web_page_preview": "true"})
    print(f"ok {destino} -> {chat}{' (ensayo)' if cfg.get('ensayo') else ''}")


# --- self-check -----------------------------------------------------------

def self_check():
    assert [escala(x) for x in (0.6, 0.3, 0.0, -0.3, -0.6)] == [2, 1, 0, -1, -2]
    assert escala(0.25) == 1 and escala(-0.20) == -1 and escala(-0.19) == 0
    assert nota({"redes": (0.3, 54)}, {"redes": (0.2, 12)}) == 2           # +50 % exacto
    assert nota({"redes": (0.3, 54), "digitales": (0.7, 32)},
                {"redes": (0.2, 12), "digitales": (5.2, 76)}) == 0          # +2 y −2 -> 0
    assert nota({"redes": (2, 99), "digitales": (1, 99)}, {"redes": (2, 99), "digitales": (2, 99)}) == -1  # 0 y −2
    base = {"fecha": "2026-10-26", "volumen": {"redes": 6000, "digitales": 1500, "analogico": 30},
            "temas": {t: {"redes": 1.0, "digitales": 1.0, "analogico": 1} for t in TEMAS},
            "narrativas_redes": {"Fraude": 15.0, "Brasil": 17.0}, "hallazgos": [{"texto": "x"}]}
    base["temas"]["Clima"] = {"redes": 0.1, "digitales": 0.2, "analogico": 1}   # bajo mínimo también antes
    hoy = json.loads(json.dumps(base))
    hoy["fecha"] = "2026-10-27"
    hoy["temas"]["Vivienda"] = {"redes": 2.0, "digitales": 2.0, "analogico": 2}   # dobla -> +2
    hoy["temas"]["Clima"] = {"redes": 0.1, "digitales": 0.1, "analogico": 0}       # bajo mínimo -> poco dato
    hoy["narrativas_redes"] = {"Fraude": 9.0, "Encuestas": 9.6}                   # -40% -> -1, nueva, desaparece Brasil
    assert not errores(hoy), errores(hoy)
    ev = {f["tema"]: f for f in evolutivo(hoy, base)["filas"]}
    assert ev["Vivienda"]["nota"] == 2, ev["Vivienda"]
    assert ev["Clima"]["estado"] == "poco dato", ev["Clima"]
    assert ev["Fraude"]["nota"] == -1 and ev["Encuestas"]["estado"] == "NUEVA" and ev["Brasil"]["estado"] == "DESAPARECE"
    assert all(f["estado"] == "base" for f in evolutivo(base, None)["filas"])
    mal = json.loads(json.dumps(hoy))
    mal["temas"]["Vivienda"]["redes"] = 140
    assert errores(mal)
    hoy["evolutivo"] = evolutivo(hoy, base)
    hoy["maldita"] = {"resumen": "3 narrativas"}
    me, md = mensaje(hoy, "ecosistema"), mensaje(hoy, "donantes")
    assert "Maldita" not in me and "Maldita" in md and PIE in me
    assert "<html>" in informe(hoy)
    print("self-check ok")


def main():
    if "--self-check" in sys.argv:
        return self_check()
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest="cmd", required=True)
    sp.add_parser("pdftext").add_argument("pdf")
    sp.add_parser("validar").add_argument("hoy")
    p = sp.add_parser("evolutivo"); p.add_argument("hoy"); p.add_argument("anterior")
    p = sp.add_parser("mensaje"); p.add_argument("hoy"); p.add_argument("para", choices=["ecosistema", "donantes"])
    sp.add_parser("informe").add_argument("hoy")
    p = sp.add_parser("enviar"); p.add_argument("destino"); p.add_argument("--texto", required=True); p.add_argument("--pdf")
    a = ap.parse_args()
    if a.cmd == "pdftext":
        import pymupdf
        print("\n\f\n".join(pg.get_text() for pg in pymupdf.open(a.pdf)))
    elif a.cmd == "validar":
        err = errores(cargar(a.hoy))
        print("\n".join(err) or "ok")
        sys.exit(1 if err else 0)
    elif a.cmd == "evolutivo":
        d = cargar(a.hoy)
        d["evolutivo"] = evolutivo(d, None if a.anterior == "-" else cargar(a.anterior))
        Path(a.hoy).write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf8")
        for f in d["evolutivo"]["filas"]:
            print(f"{f['tema']:<40} {indicador(f)}")
    elif a.cmd == "mensaje":
        print(mensaje(cargar(a.hoy), a.para))
    elif a.cmd == "informe":
        print(informe(cargar(a.hoy)))
    elif a.cmd == "enviar":
        enviar(a.destino, Path(a.texto).read_text(encoding="utf8"), a.pdf)


if __name__ == "__main__":
    main()

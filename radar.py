"""Radar 29N: evolutivo, mensajes y envío a Telegram.

La extracción la hace Claude en la rutina: lee el PDF de Onclusive (texto vía
`pdftext`) y el DOCX/XLSX de la fuente de bulos y escribe `hoy.json` con el esquema de
SCHEMA.md. Este script hace lo determinista:

  python radar.py pdftext <onclusive.pdf>                 texto del PDF (PyMuPDF)
  python radar.py validar <hoy.json>                      sale 1 si no cuadra
  python radar.py evolutivo <hoy.json> <anterior.json|->  añade "evolutivo" a hoy.json
  python radar.py mensaje <hoy.json> ecosistema|desinformacion|donantes  texto HTML de Telegram
  python radar.py informe <hoy.json>                      HTML del PDF de donantes
  python radar.py desbrandear <in.pdf> <out.pdf>          quita logo, Komons y proveedor del PDF del proveedor
  python radar.py enviar <destino> --texto F [--pdf F]... destino: donantes|ecosistema|desinformacion|aviso
  python radar.py chats                                  ids de grupos (añade el bot y escribe algo antes)
  python radar.py adjuntos <raw> <carpeta>                saca los adjuntos de un get_message RAW de Gmail
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

PROHIBIDO = ("maldita", "onclusive", "kantar")  # regla: los proveedores no se nombran en ninguna salida


def nombra(texto):
    t = texto.lower()
    return next((p for p in PROHIBIDO if p in t), None)


# --- desbrandear el PDF del proveedor --------------------------------------

MARCAS = PROHIBIDO + ("komons", "kolecctive")  # en un PDF tampoco puede quedar el nombre del cliente
# (frase, reemplazo), de más larga a más corta. El reemplazo no debe ser más ancho que la frase.
REEMPLAZOS = [("komons.", ""), ("· Cliente: Komons Kolecctive", ""), ("Cliente: Komons Kolecctive", ""), ("Komons Kolecctive", ""),
              ("· Komons ·", "·"), ("con Komons.", ""), ("clipping de Onclusive", "clipping"),
              ("dossier Onclusive", "dossier"), ("etiquetas de Onclusive", "etiquetas de la fuente"),
              ("de Onclusive", "de la fuente")]
GENERICOS = {"onclusive": "la fuente", "kantar": "la fuente", "maldita": "la fuente", "komons": "", "kolecctive": ""}


def marcas_en(pdf):
    """Marcas que quedan en un PDF: texto, metadatos y URLs de enlaces."""
    import pymupdf
    doc = pymupdf.open(pdf)
    partes = [pg.get_text() for pg in doc] + [str(v) for v in doc.metadata.values()]
    partes += [lk.get("uri", "") for pg in doc for lk in pg.get_links()]
    return sorted({m for m in MARCAS if m in " ".join(partes).lower()})


def desbrandear(src, dst):
    """Quita logos, textos de marca y metadatos del PDF del proveedor. Sale 1 si queda alguna marca."""
    import pymupdf
    doc = pymupdf.open(src)

    def estilo(pg, r):
        for b in pg.get_text("dict", clip=r)["blocks"]:
            for ln in b.get("lines", []):
                for s in ln["spans"]:
                    return s["size"], pymupdf.sRGB_to_pdf(s["color"]), s["origin"]
        return 8, (0, 0, 0), (r.x0, r.y1)

    def quitar(pg, frase, repl):
        hits = pg.search_for(frase)
        nuevos = []
        for r in hits:
            tam, col, origen = estilo(pg, r)
            nuevos.append((repl, (r.x0, origen[1]), tam, col))
            pg.add_redact_annot(r, fill=False)
        if hits:  # una frase por pasada: al quitarla desaparecen las coincidencias más cortas
            pg.apply_redactions(images=pymupdf.PDF_REDACT_IMAGE_NONE, graphics=pymupdf.PDF_REDACT_LINE_ART_NONE)
        for txt, punto, tam, col in nuevos:  # el texto nuevo va aparte: el de la anotación se encoge hasta ser ilegible
            if txt:
                pg.insert_text(punto, txt, fontname="helv", fontsize=tam, color=col)

    for pg in doc:
        for x in pg.get_images(full=True):  # logo: imagen pequeña en la cabecera
            r = pg.get_image_bbox(x)
            if r.y1 < 120 and r.width < 250 and r.height < 80:
                pg.add_redact_annot(r, fill=False)
                pg.apply_redactions(images=pymupdf.PDF_REDACT_IMAGE_REMOVE, graphics=pymupdf.PDF_REDACT_LINE_ART_NONE)
        for frase, repl in REEMPLAZOS:
            quitar(pg, frase, repl)
        for w, repl in GENERICOS.items():
            quitar(pg, w, repl)
            quitar(pg, w.capitalize(), repl)
    doc.set_metadata({})
    doc.del_xml_metadata()
    doc.save(dst, garbage=4, deflate=True)
    quedan = marcas_en(dst)
    if quedan:
        sys.exit(f"[error] el PDF aún menciona: {', '.join(quedan)}")
    print(f"ok {dst}")


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
    sale = {k: v for k, v in d.items() if k != "fuentes"}  # "fuentes" = nombres de archivo, uso interno
    p = nombra(json.dumps(sale, ensure_ascii=False).replace('"maldita":', ""))
    if p:
        e.append(f"menciona a {p.capitalize()}: quita el nombre, sus enlaces y sus URLs")
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


def orden(f):
    """Nuevas primero, luego de más subida a más bajada, al final las que desaparecen."""
    return {"NUEVA": -9, "DESAPARECE": 9}.get(f["estado"], -(f["nota"] or 0))


def se_mueve(ev):
    return sorted((f for f in ev if f["estado"] in ("NUEVA", "DESAPARECE") or (f["nota"] or 0) != 0), key=orden)


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


NUM = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣"]


def emoji_ev(f):
    """Indicador del evolutivo para Telegram (el PDF usa ▲●▼)."""
    if f["nota"] is None:
        return {"NUEVA": "🆕 nueva", "DESAPARECE": "💨 desaparece"}.get(f["estado"], "⚪ " + f["estado"])
    return {2: "🚀 +2", 1: "📈 +1", 0: "➖ 0", -1: "📉 −1", -2: "🔻 −2"}[f["nota"]]


def _monitoreo(d):
    ev = {f["tema"]: f for f in d.get("evolutivo", {}).get("filas", [])}
    falta = d.get("pendiente", [])
    L = [f"🗳️ <b>Radar 29N · {fecha_larga(d['fecha'])}</b>",
         f"⏳ Faltan <b>{(ELECCIONES - date.fromisoformat(d['fecha'])).days} días</b> para el 29N"]
    if falta:
        L.append(f"⚠️ <i>{e(', '.join(falta))}: pendiente, se completará mañana.</i>")
    if d.get("tono"):
        L += ["", f"🌡️ <b>Cómo está la conversación</b>", e(d["tono"])]
    if d.get("hallazgos"):
        L += ["", "🔎 <b>Cinco hallazgos del día</b>"]
        L += [f"{NUM[i]} {e(h['texto'])}" for i, h in enumerate(d["hallazgos"][:5])]
    t = d.get("traccion")
    if t:
        L += ["", f"🔥 <b>Más tracción:</b> {e(t)}" + (f" · {emoji_ev(ev[t])}" if t in ev else "")]
    mov = se_mueve(ev.values())
    if mov:
        L += ["", "📊 <b>Qué se mueve desde ayer</b>"]
        L += [f"{emoji_ev(f)} · {e(f['tema'])}" for f in mov]
    if d.get("marcos"):
        L += ["", "🧭 <b>Marcos dominantes</b>"]
        for m in d["marcos"]:
            x = f"▪️ <b>{e(m['tema'])}</b>: {e(m['dominante'])}"
            if m.get("bloques"):
                x += f"\n    💬 {e(m['bloques'])}"
            L.append(x)
    if d.get("vigilar"):
        L += ["", "👀 <b>A vigilar</b>"]
        L += [f"📅 {e(v['fecha'] + ' · ') if v.get('fecha') else ''}{e(v['texto'])}" for v in d["vigilar"][:2]]
    return L


def _desinformacion(d):
    """Mensaje dedicado de desinformación: más extenso que el resumen del monitoreo. [] si no hay."""
    m = d.get("maldita")
    if not m:
        return []
    L = [f"🚨 <b>Desinformación electoral · {fecha_larga(d['fecha'])}</b>", e(m["resumen"])]
    if m.get("narrativas"):
        L += ["", "📌 <b>Narrativas activas</b>"] + [f"▪️ {e(n)}" for n in m["narrativas"]]
    if m.get("claims"):
        L += ["", "🧾 <b>Afirmaciones en circulación hoy</b>"] + [f"▫️ {e(c['texto'])}" for c in m["claims"]]
    if m.get("vigilar"):
        L += ["", "👀 <b>A vigilar en desinformación</b>"]
        L += [f"📅 {e(v['fecha'] + ' · ') if v.get('fecha') else ''}{e(v['texto'])}" for v in m["vigilar"]]
    return L


def mensaje(d, para):
    """ecosistema = monitoreo · desinformacion = mensaje dedicado · donantes = los dos pegados."""
    if para == "desinformacion":
        des = _desinformacion(d)
        return "\n".join(des + ["", f"<i>{PIE}</i>"]) if des else ""  # "" = sin bulos hoy: no se envía
    L = _monitoreo(d)
    if para == "donantes":
        des = _desinformacion(d)
        L += ([""] + des if des else []) + ["", "📎 Informes completos en los PDF adjuntos."]
    else:
        L += ["", "📎 Informe completo en el PDF adjunto."]
    return "\n".join(L +["", f"<i>{PIE}</i>"])


def informe(d):
    ev = d.get("evolutivo", {})
    n = iter(range(1, 10))  # numeración de secciones
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
    H.append("<h2>Resumen</h2>")
    if d.get("tono"):
        H.append(f"<p><b>Cómo está la conversación.</b> {e(d['tono'])}</p>")
    if d.get("traccion"):
        H.append(f"<p><b>Más tracción.</b> {e(d['traccion'])}</p>")
    mov = se_mueve(ev.get("filas", []))
    if mov:
        H.append("<p><b>Qué se mueve desde ayer</b></p><ul>")
        H += [f"<li>{e(indicador(f).lower() if f['nota'] is None else indicador(f))} · {e(f['tema'])}</li>" for f in mov]
        H.append("</ul>")
    if d.get("maldita"):
        H.append(f"<p><b>Desinformación.</b> {e(d['maldita']['resumen'])}</p>")
    if d.get("vigilar"):
        H.append("<p><b>A vigilar</b></p><ul>")
        H += [f"<li>{e(v['fecha'] + ' · ') if v.get('fecha') else ''}{e(v['texto'])}</li>" for v in d["vigilar"][:3]]
        H.append("</ul>")
    # página aparte: Google Docs respeta page-break-before al importar el HTML
    H.append(f"<h2 style='page-break-before:always'>{next(n)}. De qué se habla: cinco hallazgos</h2><ol>")
    H += [f"<li>{e(h['texto'])}</li>" for h in d.get("hallazgos", [])[:5]]
    H.append("</ol>")
    H.append(f"<h2>{next(n)}. Qué ha cambiado: evolutivo</h2>")
    if ev.get("comparado_con"):
        H.append(f"<p>Frente al informe del {e(fecha_larga(ev['comparado_con']))}. "
                 "Variación de cuota por bloque: ≥+50% → +2 · +25..50% → +1 · −20..+25% → 0 · −50..−20% → −1 · ≤−50% → −2.</p>")
    else:
        H.append("<p>Primer informe: línea base, sin variación.</p>")
    H.append("<table><tr><th>Tema</th><th>Redes %</th><th>Digitales %</th><th>Analógico</th><th>Evolutivo</th></tr>")
    for f in sorted(ev.get("filas", []), key=orden):
        t = d["temas"].get(f["tema"], {})
        r = d.get("narrativas_redes", {}).get(f["tema"]) if f.get("narrativa") else t.get("redes")
        cel = lambda x: "—" if x is None else e(x)
        H.append(f"<tr><td>{e(f['tema'])}{' (narrativa)' if f.get('narrativa') else ''}</td><td>{cel(r)}</td>"
                 f"<td>{cel(t.get('digitales'))}</td><td>{cel(t.get('analogico'))}</td><td>{e(indicador(f))}</td></tr>")
    H.append("</table>")
    if d.get("marcos"):
        H.append(f"<h2>{next(n)}. Qué evidencia lo sostiene: marcos por tema</h2><table><tr><th>Tema</th><th>Marco dominante</th><th>Qué dice cada bloque</th></tr>")
        H += [f"<tr><td>{e(m['tema'])}</td><td>{e(m['dominante'])}</td><td>{e(m.get('bloques', ''))}</td></tr>" for m in d["marcos"]]
        H.append("</table>")
    if d.get("clima"):
        H.append(f"<h2>{next(n)}. Clima y energía</h2><p>{e(d['clima'])}</p>")
    m = d.get("maldita")
    if m:
        H.append(f"<h2>{next(n)}. Desinformación</h2><p>{e(m['resumen'])}</p><ul>")
        H += [f"<li>{e(n)}</li>" for n in m.get("narrativas", [])]
        H.append("</ul>")
        if m.get("claims"):
            H.append("<p>Claims del día:</p><ul>")
            for c in m["claims"]:
                H.append(f"<li>{e(c['texto'])}</li>")
            H.append("</ul>")
    if d.get("vigilar"):
        H.append(f"<h2>{next(n)}. A vigilar</h2><ul>")
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
    if destino in ("ecosistema", "desinformacion"):
        if not tg.get("ecosistema_chat_id"):
            sys.exit("[error] ecosistema_chat_id vacío en config.json")
        return tg["ecosistema_chat_id"], tg.get("ecosistema_thread_id" if destino == "ecosistema" else "desinformacion_thread_id")
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


def trozos(texto, n=4000):
    """Parte el texto en bloques de ≤ n caracteres cortando en líneas en blanco (Telegram admite 4.096)."""
    out, cur = [], ""
    partes = []
    for p in texto.split("\n\n"):  # un párrafo de más de n se parte por líneas
        if len(p) <= n:
            partes.append(p)
            continue
        sub = ""
        for l in p.split("\n"):
            if sub and len(sub) + len(l) + 1 > n:
                partes.append(sub)
                sub = l
            else:
                sub = f"{sub}\n{l}" if sub else l
        partes.append(sub)
    for p in partes:
        if cur and len(cur) + len(p) + 2 > n:
            out.append(cur)
            cur = p
        else:
            cur = f"{cur}\n\n{p}" if cur else p
    return out + [cur]


def enviar(destino, texto, pdfs=()):
    if destino != "aviso":  # los avisos solo los lee Cris
        p = nombra(texto)
        if p:
            sys.exit(f"[error] el mensaje menciona a {p.capitalize()}: no se envía")
        for f in pdfs:
            if marcas_en(f):
                sys.exit(f"[error] {Path(f).name} aún lleva marcas ({', '.join(marcas_en(f))}): pásalo por desbrandear")
    cfg = config()
    chat, hilo = destino_chat(destino, cfg)
    if cfg.get("ensayo") and destino != "aviso":
        texto = f"<b>[ENSAYO → {destino}]</b>\n" + texto
    base = {"chat_id": chat, "parse_mode": "HTML"}
    if hilo:
        base["message_thread_id"] = hilo
    for t in trozos(texto):
        tg_call("sendMessage", {**base, "text": t, "disable_web_page_preview": "true"})
    for f in pdfs:  # los PDF van después del texto
        tg_call("sendDocument", {k: v for k, v in base.items() if k != "parse_mode"}, f)
    print(f"ok {destino} -> {chat}{' (ensayo)' if cfg.get('ensayo') else ''}")


# --- gmail ----------------------------------------------------------------

def adjuntos(raw_path, carpeta):
    """`raw_path`: la salida de get_message con messageFormat RAW (JSON con "raw",
    tal cual la vuelca la herramienta) o el base64url suelto. Guarda los adjuntos."""
    import base64
    import email
    from email import policy
    txt = Path(raw_path).read_text(encoding="utf8").strip()
    if txt.startswith("{"):
        txt = json.loads(txt)["raw"]
    msg = email.message_from_bytes(base64.urlsafe_b64decode(txt + "=" * (-len(txt) % 4)), policy=policy.default)
    out = Path(carpeta)
    out.mkdir(parents=True, exist_ok=True)
    nombres = []
    for parte in msg.iter_attachments():
        nombre = parte.get_filename()
        if not nombre:
            continue
        nombre = Path(nombre).name  # nada de rutas que vengan en el correo
        (out / nombre).write_bytes(parte.get_payload(decode=True))
        nombres.append(nombre)
    return nombres


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
    hoy["maldita"] = {"resumen": "3 narrativas", "narrativas": ["Fraude, 12 menciones"], "vigilar": [{"texto": "huelga"}],
                      "claims": [{"texto": "c", "verificacion": "https://x"}]}
    hoy["marcos"] = [{"tema": "Vivienda", "dominante": "acceso", "bloques": "b", "fuente": "p. 2"}]
    hoy["metodologia"] = "Conversación: 6.000 menciones. Desinformación: 109 fuentes."
    me, md, mx = mensaje(hoy, "ecosistema"), mensaje(hoy, "donantes"), mensaje(hoy, "desinformacion")
    assert "3 narrativas" not in me and "Desinformación" not in me and PIE in me
    assert "3 narrativas" in md and md.index("Cinco hallazgos") < md.index("Narrativas activas") and md.count(PIE) == 1
    assert all(x in mx for x in ("3 narrativas", "Fraude, 12", "Afirmaciones", "huelga")) and "Cinco hallazgos" not in mx
    assert mensaje(dict(hoy, maldita=None), "desinformacion") == "" and "Narrativas" not in mensaje(dict(hoy, maldita=None), "donantes")
    assert "109 fuentes" in informe(hoy) and "Fuente</th>" not in informe(hoy) and "p. 2" not in informe(hoy)
    assert not any(nombra(x) for x in (me, md, mx, informe(hoy)))
    assert trozos("a\n\nb\n\nc", 4) == ["a\n\nb", "c"] and trozos("x") == ["x"]
    q = md[md.index("Qué se mueve"):md.index("Marcos") if "Marcos" in md else None]
    assert q.index("Encuestas") < q.index("Vivienda") < q.index("Fraude") < q.index("Brasil"), q
    x = informe(hoy)
    r, t = x[x.index("Resumen"):x.index("page-break")], x[x.index("<table>"):]
    assert r.index("Encuestas") < r.index("Vivienda") < r.index("Fraude") < r.index("Brasil"), r
    assert t.index("Encuestas") < t.index("Vivienda") < t.index("Fraude") < t.index("Brasil"), t
    assert "3 narrativas" in informe(hoy)[:informe(hoy).index("page-break")]
    assert not errores(hoy), errores(hoy)
    assert errores(dict(hoy, maldita={"resumen": "según Maldita.es"}))
    assert errores(dict(hoy, metodologia="Maldita Hemeroteca"))
    assert errores(dict(hoy, metodologia="Onclusive: 6.000 menciones"))
    assert errores(dict(hoy, marcos=[{"tema": "Vivienda", "dominante": "x", "fuente": "Onclusive, p. 2"}]))
    assert not errores(dict(hoy, fuentes={"onclusive": "ONCLUSIVE_27-10-2026.pdf"}))
    import base64
    import tempfile
    import pymupdf
    from email.message import EmailMessage
    with tempfile.TemporaryDirectory() as tmp:  # desbrandear: quita marcas del texto y de los metadatos, deja el resto
        doc = pymupdf.open()
        pg = doc.new_page()
        pg.insert_text((50, 50), "Cliente: Komons Kolecctive", fontsize=10)
        pg.insert_text((50, 80), "Extracción de Onclusive con 23.178 registros", fontsize=10)
        pg.insert_text((50, 110), "Informe pie · Komons · n.º 2", fontsize=10)
        doc.set_metadata({"title": "Radar Komons"})
        doc.save(Path(tmp, "a.pdf"))
        assert marcas_en(Path(tmp, "a.pdf")) == ["komons", "kolecctive", "onclusive"] or marcas_en(Path(tmp, "a.pdf"))
        desbrandear(Path(tmp, "a.pdf"), Path(tmp, "b.pdf"))
        txt = pymupdf.open(Path(tmp, "b.pdf"))[0].get_text()
        assert not marcas_en(Path(tmp, "b.pdf")) and "23.178 registros" in txt, txt
    m = EmailMessage()
    m.set_content("hola")
    m.add_attachment(b"%PDF-1.4 x", maintype="application", subtype="pdf", filename="../Informe_28-10-2026.pdf")
    with tempfile.TemporaryDirectory() as tmp:
        raw = Path(tmp, "raw.json")
        raw.write_text(json.dumps({"raw": base64.urlsafe_b64encode(m.as_bytes()).decode().rstrip("=")}), encoding="utf8")
        assert adjuntos(raw, Path(tmp, "a")) == ["Informe_28-10-2026.pdf"]
        assert Path(tmp, "a", "Informe_28-10-2026.pdf").read_bytes() == b"%PDF-1.4 x"
    print("self-check ok")


def main():
    if "--self-check" in sys.argv:
        return self_check()
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest="cmd", required=True)
    sp.add_parser("pdftext").add_argument("pdf")
    sp.add_parser("validar").add_argument("hoy")
    p = sp.add_parser("evolutivo"); p.add_argument("hoy"); p.add_argument("anterior")
    p = sp.add_parser("mensaje"); p.add_argument("hoy"); p.add_argument("para", choices=["ecosistema", "donantes", "desinformacion"])
    sp.add_parser("informe").add_argument("hoy")
    p = sp.add_parser("desbrandear"); p.add_argument("pdf"); p.add_argument("salida")
    p = sp.add_parser("enviar"); p.add_argument("destino"); p.add_argument("--texto", required=True); p.add_argument("--pdf", action="append", default=[])
    p = sp.add_parser("adjuntos"); p.add_argument("raw"); p.add_argument("carpeta")
    sp.add_parser("chats")
    a = ap.parse_args()
    if a.cmd == "chats":  # ids de los grupos donde está el bot, para config.json
        for u in tg_call("getUpdates", {})["result"]:
            m = u.get("message") or u.get("my_chat_member") or u.get("channel_post") or {}
            c = m.get("chat", {})
            print(c.get("id"), c.get("type"), c.get("title"), m.get("message_thread_id") or "")
        return
    if a.cmd == "adjuntos":
        print("\n".join(adjuntos(a.raw, a.carpeta)) or "(sin adjuntos)")
        return
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
    elif a.cmd == "desbrandear":
        desbrandear(a.pdf, a.salida)
    elif a.cmd == "enviar":
        enviar(a.destino, Path(a.texto).read_text(encoding="utf8"), a.pdf)


if __name__ == "__main__":
    main()

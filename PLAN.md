# Radar 29N · plan de construcción (27-oct)

Diseño: `DISENO.md`. Objetivo: ensayo el miércoles 28-oct a las 12:00 y salida real el jueves 29-oct.

## 0. Viabilidad (hoy)
- [ ] Rutina de prueba en la nube, de un solo disparo, sin repo. Comprueba:
  - (a) si tiene herramientas MCP de Google Drive y puede listar `Monitoring diario 29N` y leer el PDF de Onclusive;
  - (b) si hay salida de red a `api.telegram.org` y `www.googleapis.com`;
  - (c) si están disponibles Python y PyMuPDF (`pip install pymupdf`).
- [ ] Si (a) falla: añadir el conector Drive a la rutina desde claude.ai/code/routines (la sesión local no ve los conectores de claude.ai) y repetir.
- [ ] Si (a) sigue fallando: lo decide Cris. La alternativa es una cuenta de servicio de Google con la carpeta compartida.
- [ ] Si falla (b): el envío a Telegram no puede salir de la nube y hay que replantear la ejecución con Cris.

## 1. Repo `komonkris/radar-29n` (privado)
- [ ] Hacer `gh auth login` con komonkris (ahora solo aparece kikirikiworks-afk en `gh`).
- [ ] Estructura:
  - `radar.py`: extraer → evolutivo → render → enviar.
  - `templates/`
  - `data/historico/`
  - `tests/`

## 2. Núcleo (en local, con los informes del 26 y el 27-oct)
- [ ] `extract`: PDF de Onclusive a texto (PyMuPDF), y DOCX/XLSX de Maldita a texto/filas.
- [ ] Esquema JSON de cifras: volúmenes, 7 temas × 3 bloques, narrativas en redes, hallazgos, marcos por actor, fechas.
  - Claude rellena el JSON.
  - `validate()` comprueba cuotas entre 0 y 100 y que los totales cuadren con la portada.
- [ ] `evolutivo(hoy, anterior)`: escala −2..+2, umbrales mínimos, NUEVA/DESAPARECE.
  - Test con asserts usando el 26 frente al 27.
- [ ] Render del mensaje del ecosistema (≤ 2.000 caracteres) y del de donantes (ecosistema + línea de Maldita).
- [ ] PDF de donantes: HTML → Google Doc en `Informes donantes/<MES>` → export a PDF.
- [ ] Envío por Telegram (patrón de `agenda-prensa/scripts/tg.py`, copiado sin tocar el original):
  - `sendMessage` y `sendDocument`;
  - `message_thread_id` opcional;
  - interruptor `ENSAYO`, que manda todo al privado de Cris.
- [ ] Estado `data/enviado/<fecha>`, para que el envío sea idempotente entre las pasadas de 12:00, 12:30 y 13:00.
- [ ] Avisos a Cris por privado (falta un informe, parseo, Drive, Telegram).

## 3. Rutina real
- [ ] Prompt autocontenido.
- [ ] Cron `0 11 * * 1-5` UTC (12:00 Madrid, en horario de invierno desde el 25-oct). La segunda y la tercera pasada: el intervalo mínimo entre ejecuciones es de 1 h, así que van como rutinas aparte a las 12:30 y a las 13:00.
- [ ] Secretos: token del bot y chat_id (donantes, Political Watch, Cris).

## 4. Ensayo y salida
- [ ] 28-oct, 12:00: ensayo y revisión con Cris, Gabriela y Pali.
- [ ] 28-oct por la tarde: quitar `ENSAYO` si Cris da el OK.
- [ ] 29-oct, 12:00: primera salida real.

## Depende de Cris
- `gh auth login` con komonkris.
- Bot nuevo en @BotFather + "hola".
- Canal de donantes con el bot como admin.
- Que Political Watch meta el bot.

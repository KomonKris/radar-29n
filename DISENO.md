# Radar 29N · diseño del sistema (27-oct-2026)

Sale del grill-me con Cris del 27-oct. Contexto del subproyecto: `CLAUDE.md`.

## Qué hace
De lunes a viernes, a las 12:00 (hora de Madrid):
1. Lee de Drive el informe del día de Onclusive (PDF) y el de Maldita (DOCX + XLSX).
2. Genera un PDF consolidado y neutro para donantes.
3. Publica en Telegram dos mensajes:
   - a les donantes, con el PDF;
   - al ecosistema (Political Watch · Monitoreo de Actualidad), sin PDF y sin bulos.

Es **automático del todo**: no hay revisión humana antes de publicar.

## Decisiones
| # | Tema | Decisión |
|---|---|---|
| 1 | Control | Automático. El evolutivo es cuantitativo, no una valoración |
| 2 | Ejecución | Rutina en la nube (Claude Code remote trigger), no depende del portátil |
| 3 | Informes tarde | Se lanza a las 12:00, 12:30 y 13:00. Cada pasada sale si ya se envió hoy. A las 13:00 se publica con lo que haya, con la línea "X: pendiente" |
| 4 | Días | L-V. Fin de semana no hay informes |
| 5 | Donantes | Canal privado nuevo (lo crea Cris) → PDF + resumen |
| 6 | Bot | **Bot nuevo**, separado del de `agenda-prensa`, que no se toca. Claves en un archivo/secretos propios |
| 7 | Ecosistema | El bot se mete en los canales de Political Watch (lo gestiona Cris con PW). Publica directo en Monitoreo de Actualidad. Sin canal de relevo |
| 8 | PDF donantes | Propio, consolidado, 2-3 páginas, **neutro** (sin logo ni nombre de Komons) |
| 9 | Evolutivo | Mide **volumen**: variación de cuota frente al informe anterior, por bloque. Nota del tema = media de los bloques con volumen suficiente. El marco dominante va aparte, como dato descriptivo. No se pide nada más a Onclusive |
| 10 | Desinformación | **El sistema no publica en el canal de Desinformación Electoral.** Maldita solo entra en el PDF y en el mensaje de donantes |
| 11 | Comparativa de bloques | Va (qué dice PP/Vox y qué dice la izquierda de cada marco), con nota al pie fija |
| 12 | Plantilla | Una sola. Donantes = ecosistema + línea de Maldita + PDF |
| 13 | Repo | Privado, en la cuenta/org **komonkris** (la crea Cris), `komonkris/radar-29n` |
| 15 | Avisos | El bot escribe por privado a Cris **solo si algo falla o sale incompleto** |
| 17 | agenda-prensa | **Fuera.** Es otra cosa y se pausa. Solo se copia el patrón de envío (`tg.py`) |
| 18 | Alcance del evolutivo | Los 7 temas prioritarios fijos de Onclusive (Vivienda, Bulos, Voto exterior, Voto por correo, Clima, Energía, Primer voto joven) + las narrativas de "Narrativas en redes" que repiten de un día a otro. Las demás se marcan NUEVA / DESAPARECE |
| 19 | Arranque | Miércoles 28-oct en **ensayo** (todo va solo al privado de Cris). Jueves 29-oct en real si Cris da el OK |
| 20 | Estilo | Inclusivo con -e, sin firma, "Radar 29N · <fecha>", registro informativo con cifra en cada afirmación, castellano. **Telegram con emojis** en la plantilla, en títulos, números e indicadores (cambio de Cris del 27-oct). El PDF sigue neutro (▲ ● ▼) y el texto extraído no lleva emojis |

## Fórmula del evolutivo
- Δ = (cuota hoy − cuota anterior) / cuota anterior, por bloque (redes %, digitales %, analógico piezas/total).
- Escala: Δ ≥ +50 % → **+2** · +25..50 % → **+1** · −20..+25 % → **0** · −50..−20 % → **−1** · ≤ −50 % → **−2**.
- Un bloque cuenta solo si tiene ≥ 10 menciones en redes, ≥ 10 piezas en digitales o ≥ 2 piezas en analógico (hoy o en el informe anterior). Si no llega en ningún bloque, el tema sale como "poco dato". *(Umbral: decisión de Claude.)*
- Nota del tema = media de los bloques válidos, redondeada hacia cero en los medios: −1,5 → −1 y ±0,5 → 0. Cuando los bloques van en direcciones opuestas, no se exagera. *(Decisión de Claude.)* Indicador: ▲ si > 0, ● si 0, ▼ si < 0.
- Se compara con el **informe anterior disponible**, no con el día natural anterior (el lunes se compara con el viernes).
- El histórico se guarda en el repo: `data/historico/<fecha>.json`, con las cifras extraídas de Onclusive.

## Entradas
- Onclusive: `Monitoring diario 29N/Onclusive (Kantar) - Radar conversación electoral/<MES>/`, archivo que contiene `_AAAAMMDD`.
- Maldita: `Monitoring diario 29N/Maldita - Monitoreo desinformación/<MES>/`, `Maldita_MonitoreoElectoral_EG26_AAAA-MM-DD_manana.{docx,xlsx}`.
- La subcarpeta del mes (OCTUBRE, NOVIEMBRE) se crea si no existe.
- **Plan B, Gmail** (añadido el 28-oct, porque los proveedores mandan por email y no suben a Drive): si no está en Drive, se busca el correo del día en el buzón de Cris y se sacan los adjuntos con `get_message` RAW → `radar.py adjuntos`. Maldita tiene que poner a Cris en copia: el 28-oct solo lo recibió Gabriela.
- El texto del PDF se extrae con **PyMuPDF**. `read_file_content` de Drive pierde las cifras de las tablas. Comprobado el 27-oct: PyMuPDF saca "Vivienda 6,2% · 378 / 10,6% · 154 / 4".
- Claude convierte el texto en un JSON de cifras y lo valida: cuotas entre 0 y 100, totales que cuadran con la portada. Si no valida, se envía sin evolutivo y se avisa a Cris.

## Salidas
**PDF de donantes** (Google Doc en Drive → export PDF), `Monitoring diario 29N/Informes donantes/<MES>/Radar29N_donantes_AAAA-MM-DD`. Responde: de qué se habla, qué ha cambiado y qué evidencia lo sostiene.
1. Cabecera: fecha, días hasta el 29N, volúmenes (menciones, piezas digitales, piezas analógicas).
2. Los 5 hallazgos del día (de Onclusive).
3. Evolutivo: tabla de los 7 temas + narrativas repetidas, con nota −2..+2 y ▲●▼.
4. Marco dominante por tema prioritario, con lo que dice cada bloque y su fuente.
5. Clima/energía: cifra de Onclusive y, si llega, su microindicador.
6. Desinformación (Maldita): 3 narrativas principales con su evolución, claims del día con enlace de verificación. "Fuente: Fundación Maldita.es".
7. Qué vigilar y fechas (fusión de Onclusive y Maldita).
8. Nota metodológica: fuentes y volúmenes de los dos proveedores.
9. Pie fijo: "Análisis descriptivo de la conversación pública; no constituye posicionamiento."

**Mensaje del ecosistema** (≤ 2.000 caracteres): "Radar 29N · <fecha>" → tono general en una línea → 5 hallazgos (una línea y una cifra cada uno) → tema con más tracción y su evolutivo → una línea por tema prioritario con el marco dominante y qué dice cada bloque → 2 cosas a vigilar → pie fijo. Sin bulos.

**Mensaje de donantes** = mensaje del ecosistema + una línea de Maldita ("3 narrativas activas; principal X, de N a M recurrencias") + PDF adjunto.

## Fallos (aviso por privado a Cris)
Avisa en estos casos:
- falta algún informe a las 13:00;
- el PDF no se puede leer o las cifras no validan;
- Drive no responde;
- Telegram rechaza el envío.

Un día normal no se manda nada. Si no hay ningún informe a las 13:00, no se publica nada.

## Depende de Cris (bloqueante)
1. Crear la cuenta/org **komonkris** en GitHub y `gh auth login` (la sesión de kikiriki se queda).
2. Crear el **bot nuevo** en @BotFather y escribirle "hola" (para sacar su chat_id).
3. Crear el **canal de donantes** y hacer admin al bot.
4. Conseguir que **Political Watch** meta el bot en Monitoreo de Actualidad (pasarme grupo/tema para el `message_thread_id`).

## Riesgos y comprobaciones al construir
- **Drive desde la rutina en la nube**: hacer una prueba en seco antes de nada. Si no funciona, parar y decidirlo con Cris.
- **El formato de Onclusive es un "borrador prototipo"** y puede cambiar. El parser es Claude + validación, no expresiones regulares fijas.
- **PDF de Onclusive con "Komons"** en cada página: nunca se reenvía.
- **Línea no partidista**: la comparativa describe y nunca pide el voto. Si se publicara fuera de donantes y Political Watch, ⚖️ Pam.

## Pendiente (no bloquea)
- Si Maldita manda también un informe de tarde (hoy solo "_manana").
- El microindicador de clima de Onclusive (lo pide Gabriela). Si no llega, en su sección solo va la cifra de los temas Clima y Energía.

# Subproyecto · Monitoring narrativo para donantes y ecosistema

Informe diario de social listening, narrativas y bulos para el 29N. Hay dos salidas: **donantes** y **ecosistema** (Telegram de Political Watch).
Origen: reunión "Sincronización monitoring", 27-oct-2026, con Cris, Gabriela y Paula (Pali).
- Notas y transcripción: https://docs.google.com/document/d/1vLWGRuUSPC09W4rwlbdknECiwRfJkKKstkcQgcumdNM
- Contexto general de GTV: `../CLAUDE.md`

> **Regla (29-oct, petición a Cris):** Maldita no se nombra en nada que salga (mensajes, PDF, Google Docs, grupos, entregables): ni Maldita.es, ni Maldita Hemeroteca, ni la fundación, ni enlaces suyos. Su contenido se usa sin atribuir, como "desinformación". El nombre solo vale internamente para localizar archivos. `radar.py` lo bloquea en `validar` y `enviar`.

## Fuentes (llegan cada día por email, con copia a Cris, Gabriela y Paula)
| Proveedor | Qué manda | Hora | Formato |
|---|---|---|---|
| **Onclusive Social** (Miquel Pons, Beatriz López, Armando Martínez) — en la reunión y en Gemini se le llama "Kantar"/"Cantar" | "Radar conversación electoral". **3 bloques**: social listening digital · medios digitales · analógico. Incluye narrativas, actores, cruce actor×tema, **5 temas top**, evolutivo, fechas a vigilar y fuentes como nota metodológica. Dato de movilización del voto en la diapo 4 | 10:00–11:00, a diario desde el **miércoles 28-oct** (el definitivo del 27-oct llegó a las 12:00) | PDF |
| **Fundación Maldita** (Pablo Hernández Escayola, Rocío Benavente) | "Monitoreo narrativas potencialmente desinformadoras", últimas 24 h, con sección "a vigilar" | ~11:00 | DOCX + XLSX (`Maldita_MonitoreoElectoral_EG26_<fecha>_manana`) |
| **Canal Telegram propio** (TEC-20, skill `agenda-prensa`) | Agenda de 22 diarios en 5 bloques (clima, internacional/convivencia, vivienda, servicios públicos, otros), tono −2..+2 y tendencia SUBE/BAJA | 3 veces por semana | `~/.claude/skills/agenda-prensa` (envío: `scripts/tg.py`; radar RR clonado en `../avisador-gtv`) |

⚠️ **Nombre del proveedor**: en Gmail el informe viene de **Onclusive**. "Kantar" aparece en la reunión, en Gemini y en INT-17 de Coda ("Kantar para prensa y radio"). Hay que confirmar si son la misma cosa antes de nombrarlo en un entregable.

**Drive** (creado 27-oct, en INTELIGENCIA_GTV; heredan permisos del equipo Komons, sin acceso externo todavía):
- Monitoring diario 29N `1YEtEh7jXhYqw6kF0k9lheTTdcNGr4cs1` · https://drive.google.com/drive/folders/1YEtEh7jXhYqw6kF0k9lheTTdcNGr4cs1
  - Onclusive (Kantar) - Radar conversación electoral `1QZcLoeEwLtc85CHr3E3PovKOSCLC0qFy` · https://drive.google.com/drive/folders/1QZcLoeEwLtc85CHr3E3PovKOSCLC0qFy
  - Maldita - Monitoreo desinformación `1jlJq-djBoOF3KxKYNib9zJNcRsj2sDVd` · https://drive.google.com/drive/folders/1jlJq-djBoOF3KxKYNib9zJNcRsj2sDVd
- Acceso de proveedores (editor, solo en su subcarpeta): **lo gestiona Gabriela**, no compartir desde aquí. Nomenclatura: la del proveedor (p. ej. `Maldita_MonitoreoElectoral_EG26_<fecha>_manana`).

Emails de referencia (Gmail): borrador Onclusive 26-oct `1a1794545c1fc86d` · Maldita 26-oct `1a178a8dbcac1244` · Maldita 27-oct `1a17cd992154e7d6`. Los adjuntos no se pueden bajar con el conector de Gmail; hay que esperar a la carpeta de Drive.

## Qué piden les donantes (ECF)
Tres preguntas:
1. ¿De qué se habla?
2. ¿Qué ha cambiado desde ayer?
3. ¿Qué evidencia sostiene ese cambio?

Contenido:
- **Marco dominante por tema, pese a su volumen.** Ejemplo: en vivienda, ¿manda "crisis de acceso/precios" o "okupación/seguridad jurídica"? Se trabaja sobre los **5 temas top de Onclusive**, no sobre los nuestros. Si coincide con uno nuestro (p. ej. vivienda), se resalta.
- **Las 3 patas** (digital / analógico / bulos) y una **nota metodológica propia**: fuentes y volumen analizado.
- **Microindicador de temperatura climática/energética**: dice si clima o transición energética entran como argumento transversal en temas que no son de clima. Idea de Pali; lo pide Gabriela a Onclusive y nosotras lo copiamos tal cual.
- **Evolutivo propio**: valoración de Cris cada 2 días en rango **−2..+2**. ¿El ángulo narrativo gana o pierde terreno? Onclusive no lo trae; va en su sección "evolutivo" con una pincelada nuestra.
- **Actores**: cómo meten temas PP/Vox frente al bloque de izquierda. Se acordó el **enfoque comparativo de marcos**: qué dice cada bloque sobre el marco dominante. No se acordó "en qué medios sale más". Lo de los medios es lo que ya hace el Telegram por orientación de medio; se puede usar como apoyo.
- **Qué vigilar / fechas que vienen**: se fusiona lo de Maldita, lo de Onclusive y el calendario de `agenda-prensa`.

## Decisiones (27-oct, fase de **testeo**)
> ⚠️ El diseño del sistema (`DISENO.md`, grill-me del 27-oct) **manda sobre esta sección**:
> - el sistema no publica en Desinformación Electoral;
> - el ecosistema no recibe PDF;
> - el evolutivo es automático, por volumen;
> - a Onclusive no se le piden más indicadores.

- **Donantes**: 1 documento consolidado + su mensaje de Telegram.
- **Ecosistema**: el documento se parte en dos.
  - Monitoreo **sin bulos** → canal **Monitoreo de Actualidad**.
  - Bulos → canal **Desinformación Electoral** (la base es Maldita).
- De momento solo esos **2 canales generales**. Nada de subcanales por tema. Pali avisa de saturación: de 20 personas, ~15 lo leen de vez en cuando y 4–5 actúan. Se desagrega (vivienda, clima…) solo si las organizaciones lo piden. Habrá que preguntarles qué usan.
- PDF **sin logos ni nombre de Komons**. Mensaje de Telegram corto: **5 prioridades + 2 cosas a vigilar**. Quien quiera, entra al PDF.
- **Envío a las 12:00** cada día. La idea es que sea lo más automático posible.
- **Dos carpetas de Drive separadas**: Onclusive/"Kantar" y Maldita. Los proveedores suben ahí sus informes, no por email. Archivo por mes y por día.
- Evitar 50 versiones: proponer a ECF que reenvíe por email (lista de ~60 grantees y ex-grantees en España) lo mismo que va por Telegram.

## Political Watch (infraestructura del encuentro del 21-oct)
- Un canal grande de Telegram con chats pequeños por tema. Hay 5–6 canales, entre ellos un canal de **respuesta rápida** que es para las fichas.
- Seguridad: **1 admin por organización** (probablemente Saya). Pali y Cris quieren justificar 2 personas para monitoreo.
- Flujo previsto: canal **privado nuestro** donde cae la info de forma automática → la admin copia y pega en Political Watch.
- El formulario de alta a organizaciones salía el 27-oct.

## Tareas
**Cris**
- [x] Crear las 2 carpetas de Drive (27-oct). [ ] Pasar el enlace a Gabriela.
- [ ] Mandar las notas de Gemini al equipo.
- [ ] **Proponer los modelos de informe**: donantes (consolidado + mensaje Telegram) y ecosistema (Monitoreo / Desinformación).

**Gabriela**
- Pedir a Onclusive el microindicador de clima.
- Pedir a Onclusive y a Maldita que suban los informes a Drive.
- Pasar el resumen de la reunión con donantes.
- Meter a Paula (y a Cris) en la lista de Maldita.

**Pali**
- Avisar a Saya de que se iterará si los canales no sirven.

## Encaje con la línea GTV
- Es análisis interno y de ecosistema, no mensaje público.
- La comparativa de bloques (PP/Vox frente a izquierda) **describe** marcos y nunca pide voto.
- Si algo de esto se publica fuera de donantes y ecosistema, pasa por ⚖️ revisión legal (Pam).

## Relación con otras piezas
- **TEC-20** (canal Telegram de agenda mediática): esto es su evolución con fuentes profesionales.
- **RR V3** (Drive `1UcW7kJts8wiWvJylQDTodH0hqvJPe0Q0`): radar de agenda, radar de incidentes y niveles Estable/Vigilar/Alerta/Crisis.
- **KPI ECF**: 5 briefings semanales de inteligencia narrativa para 10 organizaciones.
- **MEL-06/08**: justificación ECF. Este archivo diario cuenta como evidencia.

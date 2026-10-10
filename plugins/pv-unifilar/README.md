# PvUnifilar

Plugin de Claude Code que diseña y dibuja el **diagrama unifilar de un sistema fotovoltaico interconectado en México** (CFE, NOM-001-SEDE-2012) a partir de una petición sencilla.

> "Hazme un diagrama con 8 paneles Jinko de 475 W"

En un solo paso entrega, en una carpeta por proyecto:

| Entregable | Con AutoCAD | Sin AutoCAD |
|---|---|---|
| Plano editable | DWG (y DXF) | DXF |
| Plano en PDF | ploteado por AutoCAD | generado por el plugin (A3 vectorial) |
| Memoria de cálculo | Excel con fórmulas y PDF | igual |
| Hoja de proyecto | Excel editable para el modo profesional | igual |
| Resumen de materiales | en el chat y en texto | igual |

También explica en una frase por qué eligió el inversor (prefiere una relación CD/CA entre 1.10 y 1.25).

## Instalación

Requisitos:

- **Claude Code** (terminal, escritorio o extensión del editor).
- **uv** (instala Python y las dependencias del plugin). En Windows: `winget install --id=astral-sh.uv -e`. En macOS o Linux: `curl -LsSf https://astral.sh/uv/install.sh | sh`.
- **AutoCAD** (opcional, Windows): si está instalado, el plugin entrega DWG y el PDF ploteado por AutoCAD.

En Claude Code:

```
/plugin install pv-unifilar --marketplace edu3250/Diagrama-unifilarAutoCAD
```

o en dos pasos:

```
/plugin marketplace add edu3250/Diagrama-unifilarAutoCAD
/plugin install pv-unifilar@pvsld
```

**La primera vez**, uv descarga las dependencias del servidor (unos 60 MB; de 15 a 60 segundos según la conexión). Si `/mcp` muestra el servidor `pvsld` como fallido, espera a que termine la descarga y reconéctalo desde `/mcp`. También puedes descargarlo antes, una sola vez, desde una terminal:

```
uvx --from git+https://github.com/edu3250/Diagrama-unifilarAutoCAD@v0.5.0rc1 pvsld-mcp --version
```

Después arranca en un par de segundos.

## Uso

| Comando | Para qué |
|---|---|
| `/pv-unifilar:diagrama <petición>` | Modo rápido: el diagrama completo a partir de una petición sencilla. Una petición normal en el chat también lo activa. |
| `/pv-unifilar:pro nuevo` | Una hoja de proyecto en blanco para fijar cualquier valor. |
| `/pv-unifilar:pro <proyecto u hoja.xlsx>` | Diseña con la hoja llenada; si algo no cumple, devuelve la hoja con las celdas en rojo y la razón. |
| `/pv-unifilar:catalogo <hoja técnica.pdf>` | Agrega a tu catálogo local un equipo que no está, después de que confirmas sus valores. |

**Modo rápido.** Usa valores generales para lo que no indiques: servicio CFE en baja tensión 2F-3H 220/127 V, 10 kA de corriente de falla, interruptor principal de 100 A, temperaturas típicas. Los datos personales quedan en blanco para llenarlos a mano.

**Modo profesional.** La hoja de proyecto tiene una celda amarilla por parámetro; AUTO deja que el cálculo decida. Lo que fijes (inversor, cadenas, fusibles, calibres, tubería, servicio) se respeta y se revisa contra la NOM. Los datos personales que llenes pasan al plano y a la memoria tal como los escribas.

**Catálogo local.** Los equipos que agregues se guardan en `%APPDATA%\pvsld\catalogo` (Windows) o `~/.local/share/pvsld/catalogo`, junto con su hoja técnica, y nunca salen de tu computadora.

**Carpeta de proyectos.** Por omisión, `out/` en la carpeta donde trabajas con Claude. Puedes elegir otra en la configuración del plugin (`/config`).

## Alcance y limitaciones

- Funciona en Claude Code; no en claude.ai en el navegador, porque el servidor corre en tu computadora.
- Sistemas residenciales de baja tensión, un inversor de cadena, hasta dos cadenas, servicio CFE 1F-2H o 2F-3H.
- Un equipo que no está en el catálogo necesita su hoja técnica.
- **Los planos son borradores:** un ingeniero responsable debe revisarlos y firmarlos antes de cualquier trámite.

## Licencia

MIT. Código y documentación técnica: <https://github.com/edu3250/Diagrama-unifilarAutoCAD>.

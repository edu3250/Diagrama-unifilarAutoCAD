# pvsld: el servidor de PvUnifilar

Servidor MCP y línea de comandos que diseñan y dibujan el **diagrama unifilar de un sistema fotovoltaico interconectado en México** (baja tensión, NOM-001-SEDE-2012) a partir de una petición sencilla.

> "Hazme un diagrama unifilar con 12 paneles Jinko de 475 W"

![Plano unifilar A3 de un sistema de 5.70 kWp](https://raw.githubusercontent.com/edu3250/PvUnifilar/develop/docs/images/readme/plano-unifilar.png)

Una petición entrega, en una carpeta por proyecto: el plano en DWG (con AutoCAD) o DXF, su PDF en A3, la memoria de cálculo en Excel con fórmulas y en PDF, una hoja de proyecto editable y el resumen de materiales. Un modelo de lenguaje pide y explica; el cálculo y el dibujo los hace código determinista, con equipos tomados de un catálogo de fichas revisadas contra su hoja técnica.

## Uso

Con [uv](https://docs.astral.sh/uv/) instalado, cualquier cliente MCP puede ejecutar el servidor:

```json
{
  "mcpServers": {
    "pvsld": {
      "command": "uvx",
      "args": ["--from", "pvsld", "pvsld-mcp"]
    }
  }
}
```

En Claude Code, Copilot CLI y Gemini CLI se instala como plugin o extensión, con sus comandos (`diagrama`, `pro`, `catalogo`): las instrucciones están en el [repositorio](https://github.com/edu3250/PvUnifilar) y en la [guía de usuario](https://github.com/edu3250/PvUnifilar/blob/develop/docs/guia-de-usuario.md).

Sin un modelo de por medio:

```bash
uvx --from pvsld pvsld design peticion.yaml -o out/casa
```

## Alcance

Sistemas residenciales sin baterías, un inversor de cadena, hasta dos cadenas, servicio 1F-2H o 2F-3H. AutoCAD es opcional (Windows).

**Los planos son borradores:** un ingeniero responsable debe revisarlos y firmarlos antes de cualquier trámite. Este proyecto no está afiliado a CFE, a Autodesk ni a ningún fabricante.

Licencia MIT. Código, cambios y reportes: <https://github.com/edu3250/PvUnifilar>.

---
description: Hace el diagrama unifilar de un sistema fotovoltaico interconectado (México, CFE, NOM-001-SEDE-2012) a partir de una petición sencilla como "un diagrama con 8 paneles Jinko de 475 W"; entrega el plano DWG o DXF, el PDF, la memoria de cálculo, la hoja de proyecto y el resumen de materiales. Úsala cuando pidan un diagrama unifilar, plano eléctrico o memoria de cálculo de paneles solares o de un sistema fotovoltaico.
argument-hint: "[petición, p. ej. 8 paneles Jinko 475 W]"
allowed-tools: mcp__plugin_pv-unifilar_pvsld__list_components mcp__plugin_pv-unifilar_pvsld__design_and_draw
---

# PvUnifilar: diagrama rápido

Design one grid-tied PV installation in Mexico from the user's request and deliver every file in one step. Talk to the user in Spanish.

Request: $ARGUMENTS

## Steps

1. **Find the module.** Call `list_components` with `component_type: pv_module` (add `manufacturer` when the user named one). Match the user's words (brand, model, watts) to a `component_id`.
   - One clear match: use it. Several: ask which one, listing them with their watts.
   - None: the module is not in the catalogue. Tell the user, ask for its datasheet (PDF) and follow the `catalogo` skill of this plugin to add it, then come back here.
2. **Find the size.** Use the number of modules the user gave (`module_count_min` = `module_count_max` = that number). If they gave a power instead ("un sistema de 5 kW"), pass `target_dc_power_w`. If they gave neither, ask how many modules.
3. **Only what the user said.** Pass `inverters` only when the user named an inverter (find its id with `list_components`, `component_type: string_inverter`). Pass `routing` lengths only when given. Never invent service, site or personal data: the tool's quick defaults cover them and leave personal data blank.
4. **Call `design_and_draw`** once. Give `name` only when the user named the project.
5. **When it works**, tell the user:
   - why this inverter: `explanation_es`, as it is;
   - the installation summary: `bom_text` in a code block;
   - the project folder and its files (DWG or DXF and the PDF, memoria de cálculo in Excel and PDF, hoja de proyecto, resumen de materiales);
   - that they can change any value in `hoja_de_proyecto.xlsx` and ask for `/pv-unifilar:pro` to redesign with it;
   - that the drawing is a draft a responsible engineer must review and sign.

   Look at the preview image before you answer; mention anything that looks wrong.
6. **When no configuration fits**, explain the main reasons in plain Spanish (the `sizing` text) and propose a change: more or fewer modules, another inverter, or another module.
7. **When the folder already exists**, ask before calling again with `overwrite: true`, or suggest another `name`.

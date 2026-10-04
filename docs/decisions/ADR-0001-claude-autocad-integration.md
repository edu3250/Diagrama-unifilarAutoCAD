# ADR-0001: Claude ↔ AutoCAD Integration Approach

**Status:** Pending (to be completed in Phase 1, Stage 1.4)

**Decision Date:** TBD

**Stakeholders:** edu3250

---

## Context

This Architecture Decision Record will synthesize research from Phase 1, Stages 1.2 (Official Autodesk APIs & MCP documentation) and 1.3 (Community GitHub implementations) to determine the optimal approach for integrating Claude (via the Model Context Protocol) with Autodesk AutoCAD.

## Problem Statement

Multiple viable paths exist to connect Claude to AutoCAD:

1. **AutoCAD .NET SDK + MCP Bridge** — Native .NET server hosting MCP, direct AutoCAD COM access
2. **AutoLISP + Claude API** — Lightweight AutoCAD-side scripting, external API calls
3. **Design Automation API + MCP** — Cloud-hosted, no local AutoCAD required
4. **ODA (Open Design Alliance) File Generation** — Read/write .dwg directly without AutoCAD
5. **Pure DXF/DWG File Generation (ezdxf, libredwg)** — File-based, fully decoupled from AutoCAD

Each approach has trade-offs in:
- **Latency** — Real-time interaction vs. batch processing
- **Complexity** — Implementation and deployment difficulty
- **Cost** — Licensing, cloud infrastructure
- **Compliance** — Mexican regulatory requirements (NOM-001-SEDE, CRE)
- **Maintainability** — Community support, long-term viability

## Research Summary

*(To be populated after Stage 1.2 and 1.3 research is complete)*

### Stage 1.2 Findings

- Autodesk's official documented APIs: AutoCAD .NET SDK, COM (automation), RealDWG, AutoLISP
- MCP specification and its suitability for CAD operations
- Claude tool use and function calling capabilities
- Latency and state management considerations

### Stage 1.3 Findings

- Survey of existing projects (GitHub repositories) attempting AutoCAD + LLM integration
- Lessons learned: what worked, what didn't, licensing constraints
- Alternative approaches: design automation, file-based generation, headless solutions

## Decision

*(To be finalized after research synthesis)*

**Recommended approach:** [TBD]

**Rationale:**
- [Trade-off analysis]
- [Regulatory compliance considerations]
- [Team capability and maintenance burden]
- [Cost and timeline implications]

## Consequences

### Positive

- [Benefits of chosen approach]

### Negative

- [Limitations and mitigations]

## Alternatives Considered

- [Other approaches and why they were rejected]

## Related Decisions

- ADR-0002 (tentative): Parametric PV model schema (Phase 3)
- ADR-0003 (tentative): Symbol library format (Phase 4)

---

**Vault Mirror:** `wiki/decisions/ADR-0001`

**Last Updated:** 2026-10-04

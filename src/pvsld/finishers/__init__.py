"""Optional finishers (ADR-0001): turn a B1 DXF into DWG 2018 and/or a plotted PDF.

Planned content:

* Core Console (``accoreconsole.exe``), local and Windows-only, validated in Stage 2.4. It must
  check the exit code, the output files and a timeout, because it fails silently without a licence;
* APS Automation API, opt-in, using the user's own credentials;
* ODA File Converter, opt-in, installed and licensed by the user.
"""

| Stage 2.2 criterion | Measured | Result |
|---|---|---|
| Plug-in ping p95 < 50 ms | transport 0.4 ms; via main thread 2.2 ms | PASS |
| 200 attributed inserts + 200 lines < 2 s | max 71.4 ms (p50 47.3 ms); COM p50 8779.0 ms | PASS |
| 100/100 consecutive runs without unhandled errors | plug-in 100/100; COM baseline 100/100 | PASS |
| Busy (modal dialog) -> actionable error <= 5 s, no hang | busy 'modal_dialog' in 0.00 s; recovered True (0.44 s); COM ComBusyError after 5.08 s | PASS |
| Busy (running command) -> actionable error <= 5 s, no hang | busy 'command_active' in 0.54 s; recovered True (0.06 s); COM ComBusyError after 5.00 s | PASS |
| Busy (command waiting for input) -> actionable error <= 5 s, no hang | busy 'command_active' in 1.89 s; recovered True (42.7 s); COM ComBusyError after 4.82 s | PASS |
| Injected mid-transaction failure leaves drawing unchanged | 5/5 cases unchanged (plug-in digest and COM count) | PASS |
| Client without the secret refused; pipe ACL current user only | no-auth error -32001, closed True; ACL [('deny', 'NT AUTHORITY\\NETWORK'), ('allow', '<machine>\\<user>')] | PASS |

| Operation (p50) | COM | Plug-in | COM / plug-in |
|---|---|---|---|
| ping (one round trip) | 0.8 ms | 0.7 ms | 1.2x |
| insert attributed block | 57.1 ms | 1.6 ms | 36.8x |
| read attributes | 46.7 ms | 0.8 ms | 56.2x |
| batch 200 + 200 | 8779.0 ms | 47.3 ms | 185.6x |

AutoCAD 26.0s (LMS Tech) pid 16520, started in 27.6 s, COM binding early (makepy); plug-in load 26.2 s, trust dialogs ['Seguridad - Archivo ejecutable no firmado']; shutdown closed our drawings without saving, then Quit().

# First release deployment verification

Date: 2026-11-06 (Asia/Shanghai). Application: http://192.168.31.12:18080 . Deployed source: `b136df831171bb6bbb64a948411c41c7b8ad3808`.

The deployment rebuilt only api/worker/web. The existing database container and all three named volumes were retained. DEBUG is false. Application logging is bounded, daily local maintenance is enabled, and the last pre-deployment backup `/opt/awardcollection-v1-test/backups/20261106-022637-DnI6Wx` has COMPLETE and verified checksums.

Final target PostgreSQL run: 32 tests passed in 288.775 seconds. Local complete suite: 32 passed, followed by focused download/signature regression checks. Frontend typecheck, production build and Compose validation passed.

Real browser regression used the owner and two department administrators: shared template copy, new blue background, pointer dragging, font size change, independent TEST ONLY seal uploads, competition and batch creation, XLSX import, preview, parallel department approval and automatic issuance. Partial approval did not issue certificates. Final batch 4 produced two PDFs and two PNGs with one shared publication timestamp and no task error.

Certificates 2026-AC-00005005 and 2026-AC-00005006 each contain two incremental PDF signatures. All four are mathematically intact and valid; the self-signed identity is not publicly trusted. Signature fields are invisible and do not overlay the configured seal images. The long work title is preserved. ZIP contents exactly match the four individual files. Public and administrator verification both succeeded in the browser.

Historical batch 2 remains issued with 5000 records, 5000 PDFs and 5000 PNGs. Three sampled PDF digests match the stored records and prior deployment snapshots. This is preservation verification, not a rerun of the 5000-team benchmark. Query latency during that historical generation was never measured.

The native browser automation download event was canceled on this workstation. The original attachment endpoints were instead read in the same authenticated browser session and validated by file bytes, signatures and ZIP contents. Manual browser saving is not claimed as re-tested. New worker crash/lease takeover load tests and a restore of the final full backup were not added in this round; earlier isolated restore evidence remains historical.

Evidence: target-final-audit.json, postgres-regression-final.txt, signature-verification.json, issued-5005/5006.pdf and .png, batch-4-certificates.zip, browser screenshots and verification scripts in artifacts/release-20261106. Before-fix batch 3 outputs remain separate under before-visual-fix. All fixtures are synthetic TEST ONLY data.

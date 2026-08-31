# Crown/Mast research engine reference snapshot

This directory preserves a **sanitized reference snapshot** of the user-provided controlled Crown/Mast research engine. It is architecture reference only, not the production Fast Engine.

Included in the reconstructed ZIP:

- root `README.md`
- root `pyproject.toml`
- `crown_mast_engine/**/*.py`
- `crown_mast_engine/data/*.json`

Intentionally excluded before the archive was created:

- `__pycache__` / bytecode
- the separate Korean research-document bundle
- anonymous account JSON/ZIP files
- profiles/account material and unrelated generated artifacts

The sanitized ZIP is stored as numbered base64 text parts because the GitHub connector used for this import writes UTF-8 text objects only.

Reconstruct it with:

```bash
cat crown_mast_source_sanitized.b64.part* | base64 -d > crown_mast_source_sanitized.zip
sha256sum crown_mast_source_sanitized.zip
```

Expected SHA-256:

```text
849882cc4777d21a56587405a9b115787bad8461d0b44e33892afd24b34956b9
```

The archive contains 29 source/data files and no anonymous account sample. Do not treat this specialized research engine as a general NIKKE implementation; its event/buff/damage architecture is useful as a prototype source for the new score-oriented Fast runtime.

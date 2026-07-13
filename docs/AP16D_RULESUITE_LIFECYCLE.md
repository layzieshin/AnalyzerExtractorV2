# AP-16D Regelwerk-Lifecycle

AP-16D ersetzt direktes Loeschen aktiver Regelwerke durch Inaktivieren und
 verschiebt endgueltige Entfernung von Drafts/Inaktiven nach `rules/trash/`.

## Lifecycle

- **Aktiv**: Eintrag in `rules/index.json`, Datei unter `rules/`
- **Inaktiv**: `deactivate_ruleset()` entfernt Index-Eintrag, verschiebt Datei nach `rules/inactive/`
- **Draft**: unveraendert unter `rules/drafts/`
- **Trash**: `delete_inventory_item()` fuer Drafts und Inaktive nach `rules/trash/`

## APIs

- `deactivate_ruleset(project_root, assay_key)`
- `delete_inventory_item(project_root, kind, path_or_key)` — `active` liefert `active_must_be_deactivated_first`
- `open_inactive_as_draft(project_root, inactive_path)` — Kopie nach `rules/drafts/`, kein stilles Overwrite
- `delete_ruleset()` — Kompatibilitaets-Wrapper auf `deactivate_ruleset()`
- `list_rulesuite_inventory(..., kind="inactive")`

## Rule Editor

- Filter: `Alle | Aktiv | Drafts | Inaktiv`
- `Inaktivieren...` nur fuer aktive Zeilen (Key-Bestaetigung)
- `Loeschen...` nur fuer Draft/Inaktiv
- Inaktiv bearbeiten: Kopie als Draft, nicht direkt aus `rules/inactive/`

## Grenzen

- Aktive Rules und `rules/index.json` werden durch Loeschen von Draft/Inaktiv nicht geaendert
- Kein permanentes Loeschen — nur Archivierung unter `rules/trash/`

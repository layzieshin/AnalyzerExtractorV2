import os
from pathlib import Path

from interfaces.tk.test_app import main, run_startup_smoke_check
from src.runtime.api import resolve_app_root


if __name__ == "__main__":
    app_root = resolve_app_root(Path(__file__))
    if os.getenv("ARE_SMOKE_EXIT", "").strip() == "1":
        run_startup_smoke_check(app_root)
    elif os.getenv("ARE_START_RULE_EDITOR", "").strip() == "1":
        from rule_editor_main import RuleEditorWindow

        RuleEditorWindow(project_root=app_root).mainloop()
    else:
        main(project_root=app_root)

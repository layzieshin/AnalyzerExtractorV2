from pathlib import Path

from interfaces.tk.test_app import main


if __name__ == "__main__":
    main(project_root=Path(__file__).resolve().parent)

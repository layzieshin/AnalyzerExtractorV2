if __name__ == "__main__":
    from multiprocessing import freeze_support

    # Dispatch frozen multiprocessing children before importing the UI.
    freeze_support()

from pathlib import Path

from interfaces.tk.test_app import run_entry

if __name__ == "__main__":
    run_entry(Path(__file__))

import os

from gui_min_ext import MinimalBatchGUI, run_startup_smoke_check


if __name__ == "__main__":
    if os.getenv("ARE_SMOKE_EXIT", "").strip() == "1":
        run_startup_smoke_check()
    else:
        MinimalBatchGUI().mainloop()

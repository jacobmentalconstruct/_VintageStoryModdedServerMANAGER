from pathlib import Path
from src.ui_core import UiApp


def main():
    app_dir = Path(__file__).parent
    UiApp(app_dir).run()


if __name__ == "__main__":
    main()


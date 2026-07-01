"""Launch the ODB++ Clearance Analyzer desktop GUI.

This small launcher is intended for normal Windows use and for PyInstaller
builds.  It keeps the executable entry point simple and avoids starting the CLI.
"""

from odb_clearance_analyzer.gui import main


if __name__ == "__main__":
    main()

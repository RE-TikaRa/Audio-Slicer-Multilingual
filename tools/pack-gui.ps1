$root = Split-Path -Parent $PSScriptRoot

# Activate virtual environment
& "$root\.venv\Scripts\Activate.ps1"

# Run PyInstaller
pyinstaller --onedir --noconsole --paths "$root\src" --version-file "$root\tools\file_version_info.txt" "$root\scripts\slicer-gui.py" --noconfirm

# Remove useless components
Remove-Item "$root\dist\slicer-gui\PySide6\opengl32sw.dll"
Remove-Item "$root\dist\slicer-gui\PySide6\Qt6Quick.dll"
Remove-Item "$root\dist\slicer-gui\PySide6\Qt6Pdf.dll"
Remove-Item "$root\dist\slicer-gui\PySide6\Qt6Qml.dll"
Remove-Item "$root\dist\slicer-gui\PySide6\Qt6OpenGL.dll"
Remove-Item "$root\dist\slicer-gui\PySide6\Qt6Network.dll"
Remove-Item "$root\dist\slicer-gui\PySide6\QtNetwork.pyd"
Remove-Item "$root\dist\slicer-gui\PySide6\Qt6QmlModels.dll"
Remove-Item "$root\dist\slicer-gui\PySide6\Qt6VirtualKeyboard.dll"
Remove-Item -Path "$root\dist\slicer-gui\PySide6\translations" -Recurse

# Compress files
Compress-Archive -Path "$root\dist\slicer-gui" -DestinationPath "$root\dist\slicer-gui-windows.zip" -Force

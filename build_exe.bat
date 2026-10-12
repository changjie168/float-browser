@echo off
set VENV=C:\Users\admin\.workbuddy\binaries\python\envs\default
set LIB=%VENV%\Lib\site-packages\webview\lib
set HERE=%~dp0
"%VENV%\Scripts\pyinstaller.exe" --onefile --windowed --name FloatBrowser --icon "%HERE%app.ico" --hidden-import clr --hidden-import pythonnet --collect-submodules clr_loader --add-binary "%LIB%\Microsoft.Web.WebView2.Core.dll;." --add-binary "%LIB%\Microsoft.Web.WebView2.WinForms.dll;." --add-binary "%LIB%\runtimes\win-x64\native\WebView2Loader.dll;." --add-binary "%HERE%app.ico;." --distpath "%HERE%build_exe\dist" --workpath "%HERE%build_exe\build" "%HERE%float_browser_native.py"
echo Build done at build_exe\dist\FloatBrowser.exe

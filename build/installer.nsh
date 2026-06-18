; Custom NSIS script for SanGir Automations installer.
;
; Installs the Visual C++ 2015-2022 Redistributable (x64) silently if not
; already present. This covers the MSVC runtime DLLs that DuckDB and Polars
; require. Without this, the backend exe crashes on machines that have never
; had a modern C++ application installed.

!macro customInstall
  ; Download and silently install VC++ Redist x64 if not already installed.
  ; Registry key presence means it is already installed — skip download.
  ReadRegDWORD $0 HKLM "SOFTWARE\Microsoft\VisualStudio\14.0\VC\Runtimes\x64" "Installed"
  ${If} $0 != 1
    DetailPrint "Installing Visual C++ Redistributable (required by backend)..."
    inetc::get /SILENT \
      "https://aka.ms/vs/17/release/vc_redist.x64.exe" \
      "$TEMP\vc_redist.x64.exe" \
      /END
    Pop $0
    ${If} $0 == "OK"
      ExecWait '"$TEMP\vc_redist.x64.exe" /install /quiet /norestart' $1
      DetailPrint "VC++ Redistributable install exit code: $1"
      Delete "$TEMP\vc_redist.x64.exe"
    ${Else}
      DetailPrint "VC++ download skipped (offline): $0"
    ${EndIf}
  ${Else}
    DetailPrint "Visual C++ Redistributable already installed."
  ${EndIf}
!macroend

!macro customUnInstall
  ; Nothing extra on uninstall — leave VC++ redist in place.
!macroend

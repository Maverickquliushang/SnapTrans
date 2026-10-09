Unicode true
ManifestDPIAware true
SetFont "Segoe UI" 10
!include MUI2.nsh
!include LogicLib.nsh
!include FileFunc.nsh
!include x64.nsh
!include WinVer.nsh
!include WordFunc.nsh
!include Sections.nsh
!define PRODUCT_ID "SnapTrans.Desktop"
!define UNINSTALL_KEY "Software\Microsoft\Windows\CurrentVersion\Uninstall\${PRODUCT_ID}"
Name "SnapTrans ${VERSION}"
OutFile "${OUTPUT}"
; Leave empty so /D takes precedence; read the 64-bit registry after SetRegView.
InstallDir ""
RequestExecutionLevel user
SetCompressor /SOLID lzma
SetCompressorDictSize 32
CRCCheck on
ShowInstDetails show
ShowUninstDetails show
BrandingText "SnapTrans · Capture / OCR / Translate"
VIProductVersion "${VERSION}.0"
VIAddVersionKey /LANG=2052 "ProductName" "SnapTrans"
VIAddVersionKey /LANG=2052 "FileDescription" "SnapTrans 安装程序"
VIAddVersionKey /LANG=2052 "FileVersion" "${VERSION}"
VIAddVersionKey /LANG=2052 "LegalCopyright" "SnapTrans contributors"
!define MUI_ICON "${PROJECT_ROOT}\assets\icon.ico"
!define MUI_UNICON "${PROJECT_ROOT}\assets\icon.ico"
!define MUI_ABORTWARNING
!define MUI_BGCOLOR "F4F7FB"
!define MUI_TEXTCOLOR "172B49"
!define MUI_HEADERIMAGE
!define MUI_HEADERIMAGE_RIGHT
!define MUI_HEADERIMAGE_BITMAP "${PROJECT_ROOT}\assets\installer\header.bmp"
!define MUI_WELCOMEFINISHPAGE_BITMAP "${PROJECT_ROOT}\assets\installer\welcome.bmp"
!define MUI_UNWELCOMEFINISHPAGE_BITMAP "${PROJECT_ROOT}\assets\installer\welcome.bmp"
!define MUI_WELCOMEPAGE_TITLE "$(SNAP_TEXT_0)"
!define MUI_WELCOMEPAGE_TEXT "$(SNAP_TEXT_1)"
!define MUI_FINISHPAGE_RUN "$INSTDIR\SnapTrans.exe"
!define MUI_FINISHPAGE_RUN_TEXT "$(SNAP_TEXT_2)"
!define MUI_FINISHPAGE_RUN_NOTCHECKED
!define MUI_UNCONFIRMPAGE_TEXT_TOP "$(SNAP_TEXT_3)"
!define MUI_DIRECTORYPAGE_TEXT_TOP "$(SNAP_TEXT_4)"
!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_LICENSE "${PROJECT_ROOT}\LICENSE"
!insertmacro MUI_PAGE_COMPONENTS
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_UNPAGE_FINISH
!insertmacro MUI_LANGUAGE "English"
!insertmacro MUI_LANGUAGE "SimpChinese"
!include "${PROJECT_ROOT}\installer\languages.nsh"

Var Arguments
Var NoStartMenu
Var NoDesktop
Var Probe
Var InstallMutex

!macro CheckRunning PREFIX
Function ${PREFIX}CheckRunning
    System::Call 'kernel32::OpenMutexW(i 0x100000, i 0, w "Local\SnapTrans-InstallGuard") p.r0'
    ${If} $0 P<> 0
        System::Call 'kernel32::CloseHandle(p r0)'
        MessageBox MB_OK|MB_ICONEXCLAMATION "$(SNAP_TEXT_5)" /SD IDOK
        SetErrorLevel 10
        Quit
    ${EndIf}
    IfFileExists "$INSTDIR\SnapTrans.exe" 0 done
    ClearErrors
    FileOpen $Probe "$INSTDIR\SnapTrans.exe" a
    ${If} ${Errors}
        MessageBox MB_OK|MB_ICONEXCLAMATION "$(SNAP_TEXT_6)" /SD IDOK
        SetErrorLevel 10
        Quit
    ${EndIf}
    FileClose $Probe
    done:
FunctionEnd
!macroend
!insertmacro CheckRunning ""
!insertmacro CheckRunning "un."

Function .onInit
    SetShellVarContext current
    SetRegView 64
    ${If} $INSTDIR == ""
        ReadRegStr $INSTDIR HKCU "${UNINSTALL_KEY}" "InstallLocation"
        ${If} $INSTDIR == ""
            StrCpy $INSTDIR "$EXEDIR\SnapTrans"
        ${EndIf}
    ${EndIf}
    ${IfNot} ${RunningX64}
    ${OrIfNot} ${AtLeastWin10}
        MessageBox MB_OK|MB_ICONSTOP "$(SNAP_TEXT_7)" /SD IDOK
        SetErrorLevel 11
        Quit
    ${EndIf}
    System::Call 'kernel32::CreateMutexW(p 0, i 0, w "Local\SnapTrans-Setup") p.r0 ?e'
    Pop $1
    StrCpy $InstallMutex $0
    ${If} $1 == 183
        MessageBox MB_OK "$(SNAP_TEXT_8)" /SD IDOK
        SetErrorLevel 12
        Quit
    ${EndIf}
    ${GetParameters} $Arguments
    ClearErrors
    ${GetOptions} $Arguments "/NOSTARTMENU" $0
    ${IfNot} ${Errors}
        StrCpy $NoStartMenu "1"
    ${EndIf}
    ClearErrors
    ${GetOptions} $Arguments "/NODESKTOP" $0
    ${IfNot} ${Errors}
        StrCpy $NoDesktop "1"
    ${EndIf}
    ; System integration is opt-in on every run, including legacy upgrades.
    ClearErrors
    ${GetOptions} $Arguments "/REGISTER" $0
    ${IfNot} ${Errors}
        SectionSetFlags 1 ${SF_SELECTED}
    ${EndIf}
    ReadRegStr $0 HKCU "${UNINSTALL_KEY}" "DisplayVersion"
    ${If} $0 != ""
        ${VersionCompare} "${VERSION}" "$0" $1
        ${If} $1 == 2
            MessageBox MB_OK|MB_ICONSTOP "$(SNAP_TEXT_9)" /SD IDOK
            SetErrorLevel 13
            Quit
        ${EndIf}
    ${EndIf}
    Call CheckRunning
FunctionEnd

Section "$(SNAP_TEXT_10)" Main
    SectionIn RO
    Call CheckRunning
    ; A nonempty directory must belong to our installer. Never replace a portable copy.
    ; IfFileExists with *.* checks DIRECTORY EXISTENCE, even when it is empty.
    ; DirState enumerates entries and skips the Windows . and .. entries.
    IfFileExists "$INSTDIR\*.*" 0 new_install
    ${DirState} "$INSTDIR" $0
    ${If} $0 == 0
        Goto new_install
    ${EndIf}
    ${If} $0 == -1
        MessageBox MB_OK|MB_ICONSTOP "$(SNAP_TEXT_11)" /SD IDOK
        SetErrorLevel 17
        Quit
    ${EndIf}
    ReadINIStr $0 "$INSTDIR\install-mode.ini" "SnapTrans" "ProductId"
    ${If} $0 != "${PRODUCT_ID}"
        MessageBox MB_OK|MB_ICONSTOP "$(SNAP_TEXT_12)" /SD IDOK
        SetErrorLevel 14
        Quit
    ${EndIf}
    ReadINIStr $0 "$INSTDIR\install-mode.ini" "SnapTrans" "Version"
    ${If} $0 != ""
        ${VersionCompare} "${VERSION}" "$0" $1
        ${If} $1 == 2
            MessageBox MB_OK|MB_ICONSTOP "$(SNAP_TEXT_13)" /SD IDOK
            SetErrorLevel 13
            Quit
        ${EndIf}
    ${EndIf}
    IfFileExists "$INSTDIR\Uninstall.exe" 0 new_install
    ExecWait '"$INSTDIR\Uninstall.exe" /S _?=$INSTDIR' $0
    ${If} $0 != 0
        MessageBox MB_OK|MB_ICONSTOP "$(SNAP_TEXT_14)" /SD IDOK
        SetErrorLevel 15
        Quit
    ${EndIf}
    new_install:
    SetOutPath "$INSTDIR"
    !include "${INSTALL_FILES}"
    WriteINIStr "$INSTDIR\install-mode.ini" "SnapTrans" "ProductId" "${PRODUCT_ID}"
    WriteINIStr "$INSTDIR\install-mode.ini" "SnapTrans" "Version" "${VERSION}"
    WriteINIStr "$INSTDIR\install-mode.ini" "SnapTrans" "DataLocation" "data"
    WriteUninstaller "$INSTDIR\Uninstall.exe"
SectionEnd

Section /o "$(SNAP_TEXT_15)" Integration
    WriteRegStr HKCU "${UNINSTALL_KEY}" "DisplayName" "SnapTrans"
    WriteRegStr HKCU "${UNINSTALL_KEY}" "DisplayVersion" "${VERSION}"
    WriteRegStr HKCU "${UNINSTALL_KEY}" "Publisher" "SnapTrans contributors"
    WriteRegStr HKCU "${UNINSTALL_KEY}" "InstallLocation" "$INSTDIR"
    WriteRegStr HKCU "${UNINSTALL_KEY}" "DisplayIcon" "$INSTDIR\SnapTrans.exe"
    WriteRegStr HKCU "${UNINSTALL_KEY}" "UninstallString" '$\"$INSTDIR\Uninstall.exe$\"'
    WriteRegStr HKCU "${UNINSTALL_KEY}" "QuietUninstallString" '$\"$INSTDIR\Uninstall.exe$\" /S'
    WriteRegDWORD HKCU "${UNINSTALL_KEY}" "NoModify" 1
    WriteRegDWORD HKCU "${UNINSTALL_KEY}" "NoRepair" 1
    WriteRegDWORD HKCU "${UNINSTALL_KEY}" "EstimatedSize" ${INSTALLED_KB}
    ${If} $NoStartMenu != "1"
        CreateDirectory "$SMPROGRAMS\SnapTrans"
        CreateShortcut "$SMPROGRAMS\SnapTrans\SnapTrans.lnk" "$INSTDIR\SnapTrans.exe"
        CreateShortcut "$SMPROGRAMS\SnapTrans\卸载 SnapTrans.lnk" "$INSTDIR\Uninstall.exe"
        WriteINIStr "$INSTDIR\install-mode.ini" "Shortcuts" "StartMenu" "1"
    ${EndIf}
SectionEnd

Section /o "$(SNAP_TEXT_16)" Desktop
    ${If} $NoDesktop != "1"
        CreateShortcut "$DESKTOP\SnapTrans.lnk" "$INSTDIR\SnapTrans.exe"
        WriteINIStr "$INSTDIR\install-mode.ini" "Shortcuts" "Desktop" "1"
    ${EndIf}
SectionEnd

Function un.onInit
    SetShellVarContext current
    SetRegView 64
    ReadINIStr $0 "$INSTDIR\install-mode.ini" "SnapTrans" "ProductId"
    ${If} $0 != "${PRODUCT_ID}"
        MessageBox MB_OK|MB_ICONSTOP "$(SNAP_TEXT_17)" /SD IDOK
        SetErrorLevel 16
        Quit
    ${EndIf}
    Call un.CheckRunning
FunctionEnd

Section "Uninstall"
    ; Compiled, explicit paths only. No recursive deletion, no wildcards, no user data.
    !include "${UNINSTALL_FILES}"
    ReadINIStr $0 "$INSTDIR\install-mode.ini" "Shortcuts" "StartMenu"
    ${If} $0 == "1"
        Delete "$SMPROGRAMS\SnapTrans\SnapTrans.lnk"
        Delete "$SMPROGRAMS\SnapTrans\卸载 SnapTrans.lnk"
        RMDir "$SMPROGRAMS\SnapTrans"
    ${EndIf}
    ReadINIStr $0 "$INSTDIR\install-mode.ini" "Shortcuts" "Desktop"
    ${If} $0 == "1"
        Delete "$DESKTOP\SnapTrans.lnk"
    ${EndIf}
    DeleteINISec "$INSTDIR\install-mode.ini" "Shortcuts"
    ReadRegStr $0 HKCU "${UNINSTALL_KEY}" "InstallLocation"
    ${If} $0 == $INSTDIR
        DeleteRegKey HKCU "${UNINSTALL_KEY}"
    ${EndIf}
    ; Keep the ownership marker when local data remains, allowing reinstall.
    IfFileExists "$INSTDIR\data\*.*" keep_marker
    Delete "$INSTDIR\install-mode.ini"
    keep_marker:
    Delete "$INSTDIR\Uninstall.exe"
    SetOutPath "$TEMP"
    RMDir "$INSTDIR"
SectionEnd

Set WshShell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
root = fso.GetParentFolderName(WScript.ScriptFullName)
launcher = root & "\SpeakAnywhere.exe"
script = root & "\speak_anywhere.py"
ensure = root & "\tools\ensure_launcher.ps1"
WshShell.Run "powershell -NoProfile -ExecutionPolicy Bypass -File """ & ensure & """", 0, True
If fso.FileExists(launcher) Then
  WshShell.Run """" & launcher & """ """ & script & """", 0, False
Else
  WshShell.Run "pythonw """ & script & """", 0, False
End If

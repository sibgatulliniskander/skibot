' Lance open-dashboard.bat sans fenetre de console (raccourci Bureau).
Set fso = CreateObject("Scripting.FileSystemObject")
bat = fso.GetParentFolderName(WScript.ScriptFullName) & "\open-dashboard.bat"
CreateObject("WScript.Shell").Run """" & bat & """", 0, False

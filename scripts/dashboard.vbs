' Lance dashboard.bat sans aucune fenetre visible (0 = cache)
Dim fso: Set fso = CreateObject("Scripting.FileSystemObject")
Dim dir: dir = fso.GetParentFolderName(WScript.ScriptFullName)
CreateObject("WScript.Shell").Run """" & dir & "\dashboard.bat""", 0, False

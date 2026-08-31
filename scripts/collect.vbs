' Lance collect.bat sans aucune fenêtre visible (0 = caché)
Dim fso: Set fso = CreateObject("Scripting.FileSystemObject")
Dim dir: dir = fso.GetParentFolderName(WScript.ScriptFullName)
CreateObject("WScript.Shell").Run """" & dir & "\collect.bat""", 0, False

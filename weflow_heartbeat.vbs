Function QuoteCommandLineArgument(value)
    QuoteCommandLineArgument = Chr(34) & Replace(CStr(value), Chr(34), Chr(92) & Chr(34)) & Chr(34)
End Function

Dim shell, fso, here, command, argument, exitCode
Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
here = fso.GetParentFolderName(WScript.ScriptFullName)
command = "powershell.exe -NoProfile -ExecutionPolicy Bypass -File " & _
    QuoteCommandLineArgument(here & "\weflow_heartbeat.ps1")
For Each argument In WScript.Arguments
    command = command & " " & QuoteCommandLineArgument(argument)
Next
exitCode = shell.Run(command, 0, True)
WScript.Quit exitCode

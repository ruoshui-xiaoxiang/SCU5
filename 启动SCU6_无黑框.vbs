' SCU6 Silent Launcher
Option Explicit

Dim WshShell, fso, strDir, pyExe, appPath, logPath, browserPath
Dim traPyPath, env, port, url, conn, Q, cmd

Set WshShell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

strDir = fso.GetParentFolderName(WScript.ScriptFullName)
port = "8300"
url = "http://127.0.0.1:" & port & "/"
Q = Chr(34)

traPyPath = "C:\Users\若水\AppData\Roaming\TRAE SOLO CN\ModularData\ai-agent\vm\tools\python\python.exe"
If fso.FileExists(traPyPath) Then
    pyExe = traPyPath
Else
    MsgBox "Python not found:" & vbCrLf & traPyPath, vbCritical, "SCU6"
    WScript.Quit 1
End If

appPath = fso.BuildPath(strDir, "server.py")
browserPath = fso.BuildPath(strDir, "open_browser.py")
If Not fso.FileExists(appPath) Then
    MsgBox "server.py not found:" & vbCrLf & appPath, vbCritical, "SCU6"
    WScript.Quit 1
End If

WshShell.CurrentDirectory = strDir
Set env = WshShell.Environment("Process")
env.Item("PYTHONUTF8") = "1"

Set conn = CreateObject("WinHttp.WinHttpRequest.5.1")
On Error Resume Next
conn.Open "GET", url, False
conn.SetTimeouts 1000, 1000, 1000, 1000
conn.Send
If Err.Number = 0 And conn.Status = 200 Then
    WshShell.Run "cmd /c start " & Q & Q & " " & Q & url & Q, 0, False
    WScript.Quit 0
End If
Err.Clear
On Error Goto 0

WshShell.Run Q & pyExe & Q & " " & Q & browserPath & Q, 0, False

logPath = fso.BuildPath(strDir, "server_output.log")
cmd = "cmd /c " & Q & Q & pyExe & Q & " " & Q & appPath & Q & " > " & Q & logPath & Q & " 2>&1" & Q
WshShell.Run cmd, 0, False

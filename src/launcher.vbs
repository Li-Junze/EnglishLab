' English Lab 静默启动器：读取 _env.txt 中的 conda 环境路径，用 pythonw 启动 GUI（无黑窗口）
Option Explicit

Dim fso, sh, root, envFile, envRoot, pyw, mainPy, ts, line

Set fso = CreateObject("Scripting.FileSystemObject")
Set sh  = CreateObject("WScript.Shell")

root    = fso.GetParentFolderName(WScript.ScriptFullName)   ' src
root    = fso.GetParentFolderName(root)                     ' 项目根目录
envFile = root & "\_env.txt"
mainPy  = root & "\main.py"

If Not fso.FileExists(mainPy) Then
    MsgBox "找不到 main.py：" & mainPy, 16, "English Lab"
    WScript.Quit
End If

If Not fso.FileExists(envFile) Then
    MsgBox "尚未初始化环境，请先运行 init.bat", 16, "English Lab"
    WScript.Quit
End If

Set ts = fso.OpenTextFile(envFile, 1, False)
line = ""
If Not ts.AtEndOfStream Then line = Trim(ts.ReadLine)
ts.Close

If line = "" Then
    MsgBox "_env.txt 内容为空，请重新运行 init.bat", 16, "English Lab"
    WScript.Quit
End If

envRoot = line
pyw = envRoot & "\pythonw.exe"

If Not fso.FileExists(pyw) Then
    MsgBox "找不到 pythonw.exe：" & pyw & vbCrLf & "请重新运行 init.bat", 16, "English Lab"
    WScript.Quit
End If

sh.CurrentDirectory = root
sh.Run """" & pyw & """ """ & mainPy & """", 1, False

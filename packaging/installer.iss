[Setup]
AppName=SL-Health-LLM-Eval Workbench
AppVersion=0.1.0
DefaultDirName={autopf}\SL-Health-LLM-Eval-Workbench
DefaultGroupName=SL-Health-LLM-Eval Workbench
OutputBaseFilename=SL-Health-LLM-Eval-Workbench-Setup
OutputDir=..\dist
Compression=lzma
PrivilegesRequired=lowest
[Files]
Source: "..\dist\SL-Health-LLM-Eval-Workbench\*"; DestDir: "{app}"; Flags: recursesubdirs
[Icons]
Name: "{group}\SL-Health-LLM-Eval Workbench"; Filename: "{app}\SL-Health-LLM-Eval-Workbench.exe"
Name: "{autodesktop}\SL-Health-LLM-Eval Workbench"; Filename: "{app}\SL-Health-LLM-Eval-Workbench.exe"

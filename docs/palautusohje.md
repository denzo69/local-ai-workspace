\# Säde v1 palautusohje



Tämä dokumentti kertoo, miten Säde v1 -pesä palautetaan uudelle koneelle tai korjatulle Windows-asennukselle.



\## 1. Tarvittavat asiat



\- Windows 11 Pro

\- Git

\- GitHub CLI

\- Python 3.12 tai uudempi

\- VS Code

\- PowerShell

\- varmuuskopio kansiosta C:\\Sade

\- pääsy GitHub-repoon



\## 2. Peruskansion palautus



Luo ensin kansio:



```powershell

New-Item -ItemType Directory -Force -Path C:\\Sade


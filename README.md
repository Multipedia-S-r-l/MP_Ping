# MP_Ping
 
## Comando per creare file exe
.venv/Scripts/pyinstaller --onefile --windowed --icon=favicon.ico --name="MP_Ping" script.py

.venv/Scripts/pyinstaller --onefile --icon=favicon.ico --name="MP_Ping" script.py

Opzione --windowed serve per evitare la creazione di una finestra con il terminale

Si può evitare di scrivere ".venv/Scripts/" per eseguire il comando nell'ambiente globale del PC anziché nell'ambiente virtuale del progetto.
PS. Ambiente virtuale sembra avere problemi con l'import di alcune librerie (tra cui portalocker)
import os
import shutil
from datetime import datetime

LOG = "/media/eiji/Compartilhamento/log_compacta.out"
now = datetime.now().strftime('%d-%m-%Y_%H-%M-%S')

def log(message):
    with open(LOG, "a") as f:
        f.write(message + "\n")

log("=================================================================")
log(f"Iniciando processo de compactação - Data/Hora: {now}")
log("=================================================================")
log("Excluindo conteúdo antigo...")
os.system("rm -rf /media/eiji/Compartilhamento/Linux/backuplinux'*'")
log("Arquivo backuplinux.tar.gz excluido")
log("=================================================================")
log(f"Compactando diretório Linux - Data/Hora: {now}")
log("Por favor aguarde, isso por levar alguns minutos.")
os.system("tar -czf /media/eiji/Compartilhamento/Linux/backuplinux.tar.gz Linux/")
log(f"Fim da compactação do backuplinux.tar.gz - Data/Hora: {now}")
log(f"Copiando o arquivo backuplinux.tar.gz para o diretório Linux no HD Externo - {now}")
os.system(f"cp -r /media/eiji/Compartilhamento/backuplinux.tar.gz /media/eiji/Gordo/Linux/backuplinux-{now}.tar.gz")
os.remove("/media/eiji/Compartilhamento/backuplinux.tar.gz")
log(f"Fim do processo - Data/Hora: {now}")
log("=================================================================")

# log("=================================================================")
# log(f"Iniciando processo de compactação - Data/Hora: {now}")
# log("=================================================================")
# log("Excluindo conteúdo antigo...")
# os.system("rm -rf /media/eiji/Compartilhamento/Windows/backupwindows*", ignore_errors=True)
# log("Arquivo backupwindows.tar.gz excluido")
# log("=================================================================")
# log(f"Compactando diretório Windows - Data/Hora: {now}")
# log("Por favor aguarde, isso por levar alguns minutos.")
# os.system("tar -czf /media/eiji/Compartilhamento/backupwindows.tar.gz Windows/")
# log(f"Fim da compactação do backupwindows.tar.gz - Data/Hora: {now}")
# log(f"Copiando o arquivo backupwindows.tar.gz para o diretório Windows no HD Externo - {now}")
# os.system(f"cp -r /media/eiji/Compartilhamento/backupwindows.tar.gz /media/eiji/Gordo/Linux/backupwindows-{now}.tar.gz")
# os.remove("/media/eiji/Compartilhamento/backupwindows.tar.gz")
# log(f"Fim do processo - Data/Hora: {now}")
# log("=================================================================")

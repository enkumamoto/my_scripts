import os
from datetime import datetime

now = datetime.now().strftime('%d-%m-%Y_%H-%M-%S')
log_file = ('/media/eiji/Gordo/log.txt')

with open(log_file, 'a') as f:
    print("=" * 65 + "\n")
    print(f"Copiando arquivo de backup do Linux para HD externo - {now}\n")
    f.write("=" * 65 + "\n")
    f.write(f"Copiando arquivo de backup do Linux para HD externo - {now}\n")
    os.system(f'cp -rf /media/eiji/Compartilhamento/Linux/backuplinux.tar.gz /media/eiji/Gordo/Linux/backuplinux-{now}.tar.gz')
    f.write(f"Fim do processo - Data/Hora: {now}\n")
    f.write("=" * 65 + "\n\n")
    print(f"Fim do processo - Data/Hora: {now}\n")
    print("=" * 65 + "\n\n")
    print('')
    print("=" * 65 + "\n")
    print(f"Copiando arquivo de backup do Windows para HD externo - {now}\n")
    f.write("=" * 65 + "\n")
    f.write(f"Copiando arquivo de backup do Windows para HD externo - {now}\n")
    os.system(f'cp -rf /media/eiji/Compartilhamento/Windows/backupwindows.tar.gz /media/eiji/Gordo/Windows/backupwindows-{now}.tar.gz')
    f.write(f"Fim do processo - Data/Hora: {now}\n")
    f.write("=" * 65 + "\n\n")
    print(f"Fim do processo - Data/Hora: {now}\n")
    print("=" * 65 + "\n\n")
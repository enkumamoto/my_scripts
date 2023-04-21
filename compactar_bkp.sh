#!/bin/bash
clear

LOG="/media/eiji/Compartilhamento/log_compacta.out"

echo "=================================================================" | tee -a $LOG
echo "Iniciando processo de compactação - Data/Hora: `date`" | tee -a $LOG
echo "=================================================================" | tee -a $LOG
echo "Excluindo backup antigo..."
rm -rf Linux/backuplinux*
echo "Arquivo backuplinux.tar.gz excluido"
echo "================================================================="
echo "Compactando diretório Linux - Data/Hora: `date`" | tee -a $LOG
echo "Por favor aguarde, isso por levar alguns minutos."
tar -czf Linux/backuplinux.tar.gz Linux/
echo "Fim da compactação do backuplinux.tar.gz - Data/Hora: `date`" | tee -a $LOG
echo "=================================================================" | tee -a $LOG
clear
echo "=================================================================" | tee -a $LOG
echo "Iniciando processo de compactação - Data/Hora: `date`" | tee -a $LOG
echo "=================================================================" | tee -a $LOG
echo "Excluindo backup antigo..."
rm -rf Windows/backupwindows*
echo "Arquivo backupwindows.tar.gz excluido"
echo "================================================================="
echo "Compactando diretório Windows  - Data/Hora: `date`" | tee -a $LOG
echo "Por favor aguarde, isso por levar alguns minutos."
tar -czf Windows/backupwindows.tar.gz Windows/
echo "Fim da compactação do backupwindows.tar.gz - Data/Hora: `date`" | tee -a $LOG
echo "Fim do processo - Data/Hora: `date`" | tee -a $LOG
echo "=================================================================" | tee -a $LOG
echo
# echo "=================================================================" | tee -a $LOG
# echo "Copiando o arquivo de backup para o HD Externo - `date`" | tee -a $LOG
# echo "Por favor aguarde, isso por levar alguns minutos."
# python3 $HOME/Documentos/Coding/meus_projetos_meus_scripts/copia_renomeia.py
# rm -rf /media/eiji/Compartilhamento/Linux/*
# rm -rf /media/eiji/Compartilhamento/Windows/*
# echo "Fim do processo - Data/Hora: `date`" | tee -a $LOG
# echo "=================================================================" | tee -a $LOG

cd
clear && screenfetch
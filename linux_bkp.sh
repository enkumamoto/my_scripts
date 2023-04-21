#!/bin/bash

LOG="/media/eiji/Compartilhamento/log_linux_bkp.out"
QLDISTRO=$(cat /etc/*-release | head -n1 | cut -c12-)

echo "=========================================" | tee -a $LOG
echo "# Relatório da Máquina: `hostname`" | tee -a $LOG
echo "# Distro: $QLDISTRO" | tee -a $LOG
echo "# Data/Hora: `date`" | tee -a $LOG
echo "# Iniciando Bacukp do Linux" | tee -a $LOG
echo "=========================================" | tee -a $LOG
echo
echo "Iniciando cópia do arquivo .bashrc - Data/Hora: `date`" | tee -a $LOG
yes | yes | cp -rf /home/eiji/.bashrc /media/eiji/Compartilhamento/Linux/bkp_bashrc
echo "Os arquivo .bashrc sendo copiados"
echo "Cópia de .bashrc realizada com sucesso - Data/Hora: `date`" | tee -a $LOG
echo "---"
sleep 1
echo "Iniciando cópia de Documentos - Data/Hora: `date`" | tee -a $LOG
yes | yes | cp -rf /home/eiji/Documentos /media/eiji/Compartilhamento/Linux
echo "Os arquivos estão sendo copiados"
echo "Cópia de Docuemntos realizada com sucesso - Data/Hora: `date`" | tee -a $LOG
echo "---"
sleep 1
echo
echo "Iniciando cópia de Música - Data/Hora: `date`" | tee -a $LOG
yes | yes | cp -rf /home/eiji/Música/ /media/eiji/Compartilhamento/Linux
echo "Os arquivos estão sendo copiados"
echo "Cópia de Música realizada com sucesso - Data/Hora: `date`" | tee -a $LOG
echo "---"
sleep 1
echo
echo "Iniciando cópia de Downloads - Data/Hora: `date`" | tee -a $LOG
yes | yes | cp -rf /home/eiji/Downloads /media/eiji/Compartilhamento/Linux
echo "Os arquivos estão sendo copiados"
echo "Cópia de Downloads realizada com sucesso - Data/Hora: `date`" | tee -a $LOG
echo "---"
sleep 1
echo
echo "Iniciando cópia de Imagens - Data/Hora: `date`" | tee -a $LOG
yes | yes | cp -rf /home/eiji/Imagens /media/eiji/Compartilhamento/Linux
echo "Os arquivos estão sendo copiados"
echo "Cópia de Imagens realizada com sucesso - Data/Hora: `date`" | tee -a $LOG
echo "---"
sleep 1
echo
echo "=========================================" | tee -a $LOG
echo "Realizado bacukp do Linux"  | tee -a $LOG
echo "Data/Hora: `date`" | tee -a $LOG
echo "=========================================" | tee -a $LOG

#!/bin/bash

DATE=$`date`

echo "=================================================================" | tee -a $LOG
echo "Copiando arquivo de backup do Linux para HD externo - `date`" | tee -a $LOG
cp -dpRf Compartilhamento/Linux/backuplinux.tar.gz /media/eiji/Gordo/Linux/backuplinux-$DATE.tar.gz
echo "Fim do processo - Data/Hora: `date`" | tee -a $LOG
echo "=================================================================" | tee -a $LOG
echo
echo "=================================================================" | tee -a $LOG
echo "Copiando arquivo de backup do Windows para HD externo - `date`" | tee -a $LOG
cp -dpRf Compartilhamento/Windows/backupwindows.tar.gz /media/eiji/Compartilhamento/Gordo/Windows/backupwindows-$DATE.tar.gz
echo "Fim do processo - Data/Hora: `date`" | tee -a $LOG
echo "=================================================================" | tee -a $LOG
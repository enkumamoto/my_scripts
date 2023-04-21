#!/bin/bash

#--------------------------------#
# Script para envio de relatório #
#    dos servidores via email    #
#                                #
# Criado por: Eiji Kumamoto Neto #
# Criado em: 11/02/2021          #
# Versão: 0.0.1 - ALPHA          #
#                                #
# Atualizado em: 22/02/2021      #
# Versão: 0.0.2 - BETA           #
#                                #
# Atualizado em: 25/02/2021      #
# Versão: 0.0.3 - BETA           #
#                                #
# Atualizado em: 22/03/2021      #
# Versão: 0.0.4 - BETA           #
#--------------------------------#

# Comando do ansible para executar script de relatório em todos os servidores Linux
ansible all -i hosts -m shell -a "./reports.sh" > servers_log.txt
sed -i '/| CHANGED | rc=0 >>/d' servers_log.txt

# Inteligência para envio de e-mail
RELATORIO=$(cat servers_log.txt)

echo "$RELATORIO" | mutt -s "Relatório dos Servidores Linux" -- eiji.kumamoto@gmail.com

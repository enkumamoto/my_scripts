#!/bin/bash
#LINUX
# 1. CPU
CPU_CORES=$(grep -c ^processor /proc/cpuinfo); \
CPU_LOAD=$(awk '{print $3}' /proc/loadavg | tr '.' ','); \
CPU_IDLE=$(vmstat 1 2 | tail -1 | awk '{print $15}'); \
CPU_USO=$(( 100 - CPU_IDLE )); \
\
# 2. RAM
RAM_DATA=$(free -g | grep Mem:); \
RAM_TOT=$(echo $RAM_DATA | awk '{print $2}'); \
RAM_FREE=$(echo $RAM_DATA | awk '{print $7}'); \
RAM_USO_PCT=$(echo $RAM_DATA | awk '{print int((($2 - $7) / $2) * 100)}'); \
\
# 3. DISCO OS
OS_DATA=$(df -BG --output=size,avail,fstype | grep -E 'xfs|ext4' | sed 's/G//g' | awk '{t+=$1; f+=$2} END {print t " " f}'); \
OS_TOT=$(echo $OS_DATA | awk '{print $1}'); \
OS_FREE=$(echo $OS_DATA | awk '{print $2}'); \
\
# 4. DISCO FÍSICO
DISK_PHYSICAL=$(lsblk -d -n -o NAME,SIZE -b | grep -E '^sd|^xvd|^vd' | awk '{s+=$2} END {print int(s/1024/1024/1024)}'); \
\
# 5. ASM
ASM_TOT="0"; ASM_FREE="0"; ORA_USER=""; \
if id "grid" &>/dev/null; then ORA_USER="grid"; elif id "oracle" &>/dev/null; then ORA_USER="oracle"; fi; \
if [ ! -z "$ORA_USER" ]; then \
   ASM_DATA=$(su - $ORA_USER -c "grep ^+ASM /etc/oratab | cut -d: -f2 | xargs -I{} sh -c 'export ORACLE_HOME={}; export PATH=\$PATH:{}/bin; asmcmd lsdg -p'" 2>/dev/null | grep MOUNTED | awk '{t+=$8; f+=$9} END {print t/1024 \" \" f/1024}'); \
   if [ ! -z "$ASM_DATA" ]; then \
       ASM_TOT=$(echo $ASM_DATA | awk '{printf "%.0f", $1}'); \
       ASM_FREE=$(echo $ASM_DATA | awk '{printf "%.0f", $2}'); \
   fi; \
fi; \
\
# 6. ZUMBI (GHOST DISK)
GHOST_DISK=$((DISK_PHYSICAL - OS_TOT - ASM_TOT)); \
[ $GHOST_DISK -lt 0 ] && GHOST_DISK=0; \
\
# RESULTADO FINAL
echo -e "\n--- ORAEX CAPACITY BRASIL V5.3 ---"; \
echo "CPU_Qtd;CPU_Uso;CPU_Load;RAM_Tot;RAM_Livre;RAM_Uso;Fisico_Tot;OS_Tot;OS_Livre;ASM_Tot;ASM_Livre;Zumbi"; \
echo "$CPU_CORES;$CPU_USO;$CPU_LOAD;$RAM_TOT;$RAM_FREE;$RAM_USO_PCT;$DISK_PHYSICAL;$OS_TOT;$OS_FREE;$ASM_TOT;$ASM_FREE;$GHOST_DISK"

cat /etc/redhat-release

# Função para criar linhas de separação
print_separator() {
    printf "+%s+%s+%s+%s+\n" "$(printf '%0.s-' {1..30})" "$(printf '%0.s-' {1..10})" "$(printf '%0.s-' {1..40})" "$(printf '%0.s-' {1..30})"
}

print_simple_separator() {
    printf "+%s+\n" "$(printf '%0.s-' {1..120})"
}

# Função para verificar processo e versão
check_process_and_version() {
    local process_name=$1
    local version_command=$2
    local count=$(ps -ef | grep -v grep | grep -c "$process_name")
    
    echo "| $process_name                                                                    |"
    print_simple_separator
    
    if [ $count -gt 0 ]; then
        printf "| %-20s | %-10s | %-40s | %-30s |\n" "USUARIO" "PID" "COMANDO" "STATUS"
        print_separator
        ps -ef | grep -v grep | grep "$process_name" | head -5 | while read line; do
            user=$(echo $line | awk '{print $1}')
            pid=$(echo $line | awk '{print $2}')
            cmd=$(echo $line | awk '{for(i=8;i<=NF;i++) printf "%s ", $i; print ""}' | cut -c1-40)
            printf "| %-20s | %-10s | %-40s | %-30s |\n" "$user" "$pid" "$cmd" "RUNNING"
        done
        
        if [ $count -gt 5 ]; then
            echo "| ... e mais $((count - 5)) processo(s)                                                  |"
        fi
        
        # Verificar versão
        if [ ! -z "$version_command" ]; then
            echo "|--------------------------------------------------------------------------|"
            echo "| VERSÃO:                                                                   |"
            eval "$version_command" 2>&1 | head -3 | while read version_line; do
                printf "|   %-116s |\n" "$version_line"
            done
        fi
    else
        printf "| %-116s |\n" "STATUS: PROCESSO NÃO ENCONTRADO"
    fi
    print_simple_separator
}

# Cabeçalho principal
echo "+==============================================================================+"
echo "|                    HEALTH CHECK SERVIDOR - PROCESSOS E VERSÕES              |"
echo "+==============================================================================+"

# [1] PORTAS EM LISTEN
echo -e "\n| [1] PORTAS EM LISTEN                                                       |"
print_simple_separator
printf "| %-20s | %-10s | %-15s | %-20s | %-40s |\n" "PROTOCOLO" "PORTA" "ESTADO" "PROGRAMA" "VERSÃO"
print_simple_separator
netstat -vantup 2>/dev/null | grep LIST | head -10 | while read line; do
    if [[ $line =~ (tcp|udp) ]]; then
        proto=$(echo $line | awk '{print $1}')
        port=$(echo $line | awk '{print $4}' | awk -F: '{print $NF}')
        state=$(echo $line | awk '{print $6}')
        program=$(echo $line | grep -oP '[0-9]+/\K[^ ]+' || echo "desconhecido")
        
        # Tentar detectar versão do programa
        version=""
        case $program in
            *httpd*) version=$(httpd -v 2>/dev/null | head -1 | cut -d'/' -f2 | cut -d' ' -f1) ;;
            *nginx*) version=$(nginx -v 2>&1 | cut -d'/' -f2) ;;
            *mysql*) version=$(mysql --version 2>/dev/null | cut -d' ' -f5 | cut -d',' -f1) ;;
            *postgres*) version=$(psql --version 2>/dev/null | cut -d' ' -f3) ;;
            *) version="-" ;;
        esac
        printf "| %-20s | %-10s | %-15s | %-20s | %-40s |\n" "$proto" "$port" "$state" "$program" "$version"
    fi
done
print_simple_separator

# [2] PROCESSOS E VERSÕES
echo -e "\n| [2] PROCESSOS IMPORTANTES E SUAS VERSÕES                                  |"
print_simple_separator

# HTTPD
check_process_and_version "httpd" "httpd -v 2>&1 | head -1"

# JAVA
check_process_and_version "java" "java -version 2>&1"

# ORACLE PMON
check_process_and_version "pmon" "ps -ef | grep pmon | grep -v grep | head -1 | awk '{print \$8}' | xargs -I{} {} -V 2>&1 | head -1"

# MYSQL
check_process_and_version "mysql" "mysql --version 2>&1"

# MONGO
check_process_and_version "mongo" "mongod --version 2>&1 | head -1"

# POSTGRES
check_process_and_version "postgres" "psql --version 2>&1"

# DOCKER
check_process_and_version "docker" "docker --version 2>&1"

# NODE
check_process_and_version "node" "node --version 2>&1"

# MARIADB
check_process_and_version "mariadb" "mariadb --version 2>&1 | head -1"

# CASSANDRA
check_process_and_version "cassandra" "cassandra -v 2>&1"

# RABBITMQ
check_process_and_version "rabbitmq" "cassandra -v 2>&1"

# [3] JAVA E JDK DETALHADOS
echo -e "\n| [3] JAVA E JDK - INFORMAÇÕES DETALHADAS                                  |"
print_simple_separator

# Java Runtime
echo "| JAVA RUNTIME:                                                              |"
java -version 2>&1 | while read line; do
    printf "|   %-116s |\n" "$line"
done

# JDK Packages
echo "|--------------------------------------------------------------------------|"
echo "| JDK PACKAGES INSTALADOS:                                                 |"
jdk_count=0
rpm -qa | grep -E 'jdk|java' | while read package; do
    printf "|   %-116s |\n" "$package"
    ((jdk_count++))
done
if [ $jdk_count -eq 0 ]; then
    printf "|   %-116s |\n" "NENHUM PACOTE JDK/JAVA ENCONTRADO"
fi
print_simple_separator

# [4] RESUMO DAS VERSÕES ENCONTRADAS
echo -e "\n| [4] RESUMO DAS VERSÕES - SERVIDOR                                       |"
print_simple_separator
printf "| %-25s | %-40s | %-40s |\n" "APLICAÇÃO" "VERSÃO" "STATUS"
print_simple_separator

# Função para extrair versão de forma limpa
get_version() {
    local app=$1
    case $app in
        "httpd") httpd -v 2>&1 | head -1 | sed 's/Server version: //' | cut -d'/' -f2 ;;
        "java") java -version 2>&1 | head -1 | cut -d'"' -f2 ;;
        "mysql") mysql --version 2>&1 | cut -d' ' -f5 | cut -d',' -f1 ;;
        "mongo") mongod --version 2>&1 | grep -i "db version" | cut -d'v' -f2 | cut -d' ' -f1 ;;
        "postgres") psql --version 2>&1 | cut -d' ' -f3 ;;
        "docker") docker --version 2>&1 | cut -d' ' -f3 | cut -d',' -f1 ;;
        "node") node --version 2>&1 | sed 's/v//' ;;
        "mariadb") mariadb --version 2>&1 | head -1 | cut -d' ' -f6 | cut -d',' -f1 ;;
        "cassandra") cassandra -v 2>&1 | head -1 ;;
        *) echo "-" ;;
    esac
}

# Verificar cada aplicação e seu status
for app in httpd java mysql mongo postgres docker node mariadb cassandra; do
    if pgrep -x "$app" > /dev/null || pgrep -f "$app" > /dev/null; then
        version=$(get_version "$app")
        printf "| %-25s | %-40s | %-40s |\n" "$app" "${version:-NÃO DETECTADA}" "ATIVO"
    else
        # Verificar se está instalado mas não rodando
        if command -v "$app" &> /dev/null; then
            version=$(get_version "$app")
            printf "| %-25s | %-40s | %-40s |\n" "$app" "${version:-INSTALADO}" "INSTALADO (NÃO ATIVO)"
        else
            printf "| %-25s | %-40s | %-40s |\n" "$app" "-" "NÃO INSTALADO"
        fi
    fi
done

# Oracle PMON específico
if pgrep -f "pmon" > /dev/null; then
    oracle_version=$(ps -ef | grep pmon | grep -v grep | head -1 | grep -oP 'ora_pmon_\K[^ ]+' || echo "Oracle DB")
    printf "| %-25s | %-40s | %-40s |\n" "oracle_pmon" "$oracle_version" "ATIVO"
else
    printf "| %-25s | %-40s | %-40s |\n" "oracle_pmon" "-" "NÃO ENCONTRADO"
fi

print_simple_separator

# RESULTADO FINAL
echo -e "\n--- ORAEX CAPACITY BRASIL V5.3 ---"; \
echo "CPU_Qtd;CPU_Uso;CPU_Load;RAM_Tot;RAM_Livre;RAM_Uso;Fisico_Tot;OS_Tot;OS_Livre;ASM_Tot;ASM_Livre;Zumbi"; \
echo "$CPU_CORES;$CPU_USO;$CPU_LOAD;$RAM_TOT;$RAM_FREE;$RAM_USO_PCT;$DISK_PHYSICAL;$OS_TOT;$OS_FREE;$ASM_TOT;$ASM_FREE;$GHOST_DISK"

cat /etc/redhat-release

rpm -qa | grep oracle
rpm -qa | grep java
rpm -qa | grep jdk
rpm -qa | grep mongodb
rpm -qa | grep rabbit


# Rodapé
echo -e "\n+==============================================================================+"
echo "|                              FIM DO RELATÓRIO                                 |"
echo "+==============================================================================+"
 
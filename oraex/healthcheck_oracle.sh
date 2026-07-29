#!/bin/bash

LOG_DIR="/var/log/healthcheck"
RETENTION_DAYS=20
LIMITE_DISCO=85
LIMITE_MEM=90
LISTENER_PORT="1521"
PMON_PATTERN="ora_pmon_"

export LC_ALL=C
mkdir -p "$LOG_DIR"
LOG="${LOG_DIR}/oracle_$(hostname -s)_$(date +%Y%m%d_%H%M%S).log"

# Verifica se uma porta esta em LISTEN; usa "sport = :P" para nao casar 1521 com 15210
check_port() {
  local port=$1
  ss -tln "sport = :${port}" 2>/dev/null | grep -q LISTEN \
    && echo "porta ${port}: LISTEN" \
    || echo "  [ALERTA] porta ${port} sem LISTEN"
}

# Coleta e arquiva informacoes do sistema e do Oracle
{
echo "===== HEALTH CHECK ORACLE — $(hostname -s) — $(date '+%F %T') ====="

echo "--- Sistema ---"
[ -r /etc/redhat-release ] && cat /etc/redhat-release
echo "Uptime: $(uptime -p 2>/dev/null || uptime)"

echo "--- Carga / CPU ---"
CPU_TOTAL=$(nproc)
CPU_USO=$(awk -v n="$CPU_TOTAL" '{printf "%.0f", ($1/n)*100}' /proc/loadavg)
echo "CPUs: ${CPU_TOTAL} | Load(1/5/15): $(awk '{print $1", "$2", "$3}' /proc/loadavg)"
echo "Uso de CPU (load1/CPUs): ${CPU_USO}%"

echo "--- Memoria ---"
free -h | awk 'NR==1 || /Mem|Swap/'
MEM_TOTAL_MB=$(awk '/MemTotal/{printf "%.0f", $2/1024}' /proc/meminfo)
MEM_USADA_MB=$(awk '/MemTotal/{t=$2}/MemAvailable/{a=$2} END{printf "%.0f", (t-a)/1024}' /proc/meminfo)
MEM=$(awk '/MemTotal/{t=$2}/MemAvailable/{a=$2} END{printf "%.0f",(t-a)/t*100}' /proc/meminfo)
echo "Memoria: ${MEM_USADA_MB}MB usados de ${MEM_TOTAL_MB}MB total (${MEM}%, limite ${LIMITE_MEM}%)"
[ "$MEM" -ge "$LIMITE_MEM" ] && echo "  [ALERTA] memoria acima do limite"

echo "--- Disco ---"
df -hP -x tmpfs -x devtmpfs | awk 'NR>1{printf "  %-6s usado:%-6s total:%-6s %s\n",$5,$3,$2,$6}'
df -P  -x tmpfs -x devtmpfs | awk -v L="$LIMITE_DISCO" 'NR>1{gsub("%","",$5); if($5+0>=L) print "  [ALERTA] disco "$6" em "$5"%"}'
df -Pi -x tmpfs -x devtmpfs | awk -v L="$LIMITE_DISCO" 'NR>1{gsub("%","",$5); if($5+0>=L) print "  [ALERTA] inodes "$6" em "$5"%"}'

echo "--- Processos ---"
PROC_TOTAL=$(ps -e --no-headers | wc -l)
PROC_ZUMBI=$(ps -e -o stat --no-headers | grep -c '^Z')
echo "Processos em execucao: ${PROC_TOTAL}"
echo "Processos zumbis: ${PROC_ZUMBI}"
[ "$PROC_ZUMBI" -gt 0 ] && echo "  [ALERTA] ${PROC_ZUMBI} processo(s) zumbi(s) encontrado(s)"

echo "--- Oracle (nivel SO) ---"
INST=$(ps -eo pid,args 2>/dev/null \
  | awk -v p="$PMON_PATTERN" '$2 ~ "^"p {print "  SID: "substr($2,length(p)+1)"  (PID "$1")"}')
if [ -n "$INST" ]; then
  echo "Instancia(s) detectada(s):"
  echo "$INST"
else
  echo "  [ALERTA] nenhum processo pmon encontrado (padrao: $PMON_PATTERN)"
fi
[ -r /etc/oratab ] && awk -F: '!/^#|^$/{print "  ORACLE_HOME ("$1"): "$2}' /etc/oratab

pgrep -f tnslsnr >/dev/null 2>&1 \
  && echo "Listener (tnslsnr): ATIVO" \
  || echo "  [ALERTA] Listener (tnslsnr) inativo"
check_port "$LISTENER_PORT"

ORSS=$(ps -eo rss,args 2>/dev/null | grep -E 'ora_|tnslsnr|oracle' | grep -v grep \
       | awk '{s+=$1} END{printf "%.0f", s/1024}')
[ -n "$ORSS" ] && echo "Memoria RSS agregada de processos Oracle: ${ORSS} MB"

echo "--- Resumo Capacity ---"
CPU_LOAD=$(awk '{print $3}' /proc/loadavg | tr '.' ',')
RAM_TOT=$(free -g | awk '/Mem:/{print $2}')
RAM_LIVRE=$(free -g | awk '/Mem:/{print $7}')
FISICO_TOT=$(lsblk -d -n -o NAME,SIZE -b 2>/dev/null | grep -E '^sd|^xvd|^vd' | awk '{s+=$2} END{print int(s/1024/1024/1024)}')
read -r OS_TOT OS_LIVRE <<< "$(df -BG --output=size,avail,fstype -x tmpfs -x devtmpfs 2>/dev/null | sed 's/G//g' | awk 'NR>1{t+=$1; f+=$2} END{print t+0, f+0}')"

# ASM: consulta via asmcmd, rodando como usuario grid/oracle (owner tipico do ASM)
ASM_TOT=0
ASM_LIVRE=0
ASM_USER=""
if id grid >/dev/null 2>&1; then ASM_USER=grid; elif id oracle >/dev/null 2>&1; then ASM_USER=oracle; fi
if [ -n "$ASM_USER" ]; then
  ASM_DATA=$(su - "$ASM_USER" -c "grep '^+ASM' /etc/oratab | cut -d: -f2 | xargs -I{} sh -c 'export ORACLE_HOME={}; export PATH=\$PATH:{}/bin; asmcmd lsdg -p'" 2>/dev/null \
    | awk '/MOUNTED/{t+=$8; f+=$9} END{if(t>0) printf "%.0f;%.0f", t/1024, f/1024}')
  [ -n "$ASM_DATA" ] && { ASM_TOT=${ASM_DATA%;*}; ASM_LIVRE=${ASM_DATA#*;}; }
fi

printf "%-9s %-9s %-9s %-9s %-10s %-9s %-11s %-8s %-10s %-8s %-10s %-6s\n" \
  CPU_Qtd CPU_Uso CPU_Load RAM_Tot RAM_Livre RAM_Uso Fisico_Tot OS_Tot OS_Livre ASM_Tot ASM_Livre Zumbi
printf "%-9s %-9s %-9s %-9s %-10s %-9s %-11s %-8s %-10s %-8s %-10s %-6s\n" \
  "$CPU_TOTAL" "$CPU_USO" "$CPU_LOAD" "$RAM_TOT" "$RAM_LIVRE" "$MEM" "$FISICO_TOT" "$OS_TOT" "$OS_LIVRE" "$ASM_TOT" "$ASM_LIVRE" "$PROC_ZUMBI"

echo "===== fim: $(date '+%F %T') ====="
} >> "$LOG" 2>&1

# Limpeza de logs antigos
find "$LOG_DIR" -name 'oracle_*.log' -mtime +"$RETENTION_DAYS" -delete 2>/dev/null

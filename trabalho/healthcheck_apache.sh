#!/bin/bash

# Config
LOG_DIR="/var/log/healthcheck"
RETENTION_DAYS=20
LIMITE_DISCO=85
LIMITE_MEM=90
APACHE_SERVICE="httpd"
APACHE_PORTS="80 443"
SPRING_PATTERN="spring-batch"
SPRING_PORT="8080"

export LC_ALL=C
mkdir -p "$LOG_DIR"
LOG="${LOG_DIR}/apache_$(hostname -s)_$(date +%Y%m%d_%H%M%S).log"

# Verifica se uma porta esta em LISTEN; usa "sport = :P" para nao casar 80 com 8080
check_port() {
  local port=$1
  ss -tln "sport = :${port}" 2>/dev/null | grep -q LISTEN \
    && echo "porta ${port}: LISTEN" \
    || echo "  [ALERTA] porta ${port} sem LISTEN"
}

# Coleta e arquiva informacoes do sistema e do Apache
{
echo "===== HEALTH CHECK APACHE — $(hostname -s) — $(date '+%F %T') ====="

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

echo "--- Apache (httpd) ---"
systemctl is-active "$APACHE_SERVICE" >/dev/null 2>&1 \
  && echo "servico $APACHE_SERVICE: ATIVO" \
  || echo "  [ALERTA] servico $APACHE_SERVICE inativo"
for P in $APACHE_PORTS; do
  check_port "$P"
done
echo "Processos httpd em execucao: $(pgrep -c -x httpd 2>/dev/null || echo 0)"
command -v httpd >/dev/null 2>&1 && echo "Versao: $(httpd -v 2>/dev/null | awk -F/ '/version/{print $2}' | awk '{print $1}')"
[ -r /var/log/httpd/error_log ] && { echo "Ultimos erros (httpd):"; tail -3 /var/log/httpd/error_log; }

echo "--- Spring Batch ---"
if pgrep -f "$SPRING_PATTERN" >/dev/null 2>&1; then
  echo "Spring Batch: ATIVO (PID $(pgrep -f "$SPRING_PATTERN" | tr '\n' ' '))"
else
  echo "  [ALERTA] Spring Batch nao encontrado (padrao: $SPRING_PATTERN)"
fi
[ -n "$SPRING_PORT" ] && check_port "$SPRING_PORT"
command -v java >/dev/null 2>&1 && echo "Versao Java: $(java -version 2>&1 | head -1 | cut -d'"' -f2)"

echo "--- Resumo Capacity ---"
CPU_LOAD=$(awk '{print $3}' /proc/loadavg | tr '.' ',')
RAM_TOT=$(free -g | awk '/Mem:/{print $2}')
RAM_LIVRE=$(free -g | awk '/Mem:/{print $7}')
FISICO_TOT=$(lsblk -d -n -o NAME,SIZE -b 2>/dev/null | grep -E '^sd|^xvd|^vd' | awk '{s+=$2} END{print int(s/1024/1024/1024)}')
read -r OS_TOT OS_LIVRE <<< "$(df -BG --output=size,avail,fstype -x tmpfs -x devtmpfs 2>/dev/null | sed 's/G//g' | awk 'NR>1{t+=$1; f+=$2} END{print t+0, f+0}')"
# Sem ASM neste servidor (Oracle roda apenas no servidor de banco)
ASM_TOT=0
ASM_LIVRE=0
printf "%-9s %-9s %-9s %-9s %-10s %-9s %-11s %-8s %-10s %-8s %-10s %-6s\n" \
  CPU_Qtd CPU_Uso CPU_Load RAM_Tot RAM_Livre RAM_Uso Fisico_Tot OS_Tot OS_Livre ASM_Tot ASM_Livre Zumbi
printf "%-9s %-9s %-9s %-9s %-10s %-9s %-11s %-8s %-10s %-8s %-10s %-6s\n" \
  "$CPU_TOTAL" "$CPU_USO" "$CPU_LOAD" "$RAM_TOT" "$RAM_LIVRE" "$MEM" "$FISICO_TOT" "$OS_TOT" "$OS_LIVRE" "$ASM_TOT" "$ASM_LIVRE" "$PROC_ZUMBI"

echo "===== fim: $(date '+%F %T') ====="
} >> "$LOG" 2>&1

# Limpeza de logs antigos
find "$LOG_DIR" -name 'apache_*.log' -mtime +"$RETENTION_DAYS" -delete 2>/dev/null

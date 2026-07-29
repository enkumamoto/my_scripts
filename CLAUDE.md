# CLAUDE.md

Contexto para trabalhar (IA ou humano) neste repositório de health check de servidores RHEL.

## O que é

Dois scripts Bash independentes que fazem checagem de saúde em nível de SO, rodam via cron e gravam um log por execução (nomeado com data/hora), com limpeza automática dos logs antigos.

- `trabalho/healthcheck_apache.sh` — servidor de aplicação: **Apache (httpd) + Spring Batch**.
- `trabalho/healthcheck_oracle.sh` — servidor de banco: **Oracle DB** (apenas nível SO, sem `sqlplus`).

Cada script tem um tronco comum (sistema, carga/CPU, memória, disco, inodes), um bloco final específico do serviço e um "Resumo Capacity" (tabela de capacity com CPU/RAM/disco/ASM/zumbis) no final do log.

Além dos scripts Bash, `trabalho/capacity_apache.py` é uma ferramenta Python separada (roda na máquina do analista, não no servidor RHEL) que lê os logs gerados por `healthcheck_apache.sh` e gera uma planilha `.xlsx` de capacity planning (baseline medida + sizing do servidor novo).

Os scripts `trabalho/*` ficam agrupados na pasta `trabalho/` (suíte de health check/capacity Oracle/Apache). Os utilitários avulsos em `meus_scripts/` (`comparar_e_colar.py`, `formatar_hd_exfat.py`, `aws_cleanup.py`, `battery_health.sh`, `localiza_emove.py`) não fazem parte dessa suíte — são scripts pessoais soltos (comparação/backup de pastas, formatação de HD externo em exFAT, limpeza destrutiva de conta AWS, diagnóstico de saúde de bateria em Linux e organização de PDF/DOC/XLS por conteúdo). Ver `meus_scripts/README.md` para detalhes de uso de cada um.

## Ambiente alvo

- RHEL 7, 8 e 9 (versão "mista/desconhecida") — o código é agnóstico à versão.
- Bash 4+, ferramentas base: `awk`, `ss`, `df`, `free`, `pgrep`, `ps`, `systemctl`.
- Rodar como **root** (para enxergar dono de porta e ler logs de serviço).

## Estrutura

```
.
├── trabalho/
│   ├── healthcheck_apache.sh    # servidor App
│   ├── healthcheck_oracle.sh    # servidor Oracle
│   ├── capacity_apache.py       # gera planilha .xlsx de capacity a partir dos logs do healthcheck_apache.sh
│   ├── capacity_apache.xlsx     # planilha gerada de exemplo/uso corrente
│   ├── old_capacity_script.sh   # script legado que inspirou o "Resumo Capacity"
│   └── requirements.txt         # dependencias Python do capacity_apache.py
├── meus_scripts/
│   ├── comparar_e_colar.py      # compara pasta de origem com backup e copia o que falta
│   ├── formatar_hd_exfat.py     # formata HD/pendrive externo em exFAT (macOS)
│   ├── aws_cleanup.py           # remove permanentemente recursos de uma conta AWS (sandbox/teste)
│   ├── battery_health.sh        # diagnostico de saude da bateria em notebooks Linux
│   ├── localiza_emove.py        # organiza PDF/DOC/XLS por conteudo, remove pastas vazias
│   └── README.md                # uso detalhado de cada script desta pasta
├── CLAUDE.md                    # este arquivo
└── .claude/SKILLS.md            # catálogo de checagens + runbook de alertas (suíte trabalho)
```

Não há build. Os scripts Bash são autocontidos; toda configuração fica em variáveis no topo de cada arquivo. O `capacity_apache.py` depende apenas de `openpyxl` (ver `trabalho/requirements.txt`).

### Rodar o capacity_apache.py

```bash
cd trabalho
python3 -m venv .venv && source .venv/bin/activate   # opcional, mas recomendado
pip install -r requirements.txt

python capacity_apache.py                              # usa PASTA_LOGS configurado no topo do arquivo
python capacity_apache.py ./logs -o capacity.xlsx       # pasta e saida explicitas
python capacity_apache.py ./logs --rps 250 --ms-por-req 22 --crescimento 2.0
```

Ajuste o bloco `CONFIGURACAO` no topo do arquivo (principalmente `PASTA_LOGS`) ou passe tudo por linha de comando. A planilha gerada tem 2 abas — `Dados_Brutos` e `Dimensionamento` (esta última concentra o antigo conteúdo do Leia-me, o resumo estatístico e o sizing do servidor novo) — e as estatísticas são fórmulas vivas sobre `Dados_Brutos` — acrescentar logs novos na aba e reabrir recalcula tudo.

**Rodando pelo botão Run do VSCode (macOS/Homebrew):** o Run usa o `python3` do sistema, não um `.venv`. Se aparecer `Erro: openpyxl nao instalado`, o Homebrew bloqueia `pip install` direto no Python gerenciado por ele (PEP 668). Instale assim:

```bash
/usr/bin/env python3 -m pip install --user --break-system-packages openpyxl
```

`--user` isola a instalação do site-packages do sistema, então o `--break-system-packages` é seguro aqui.

## Configuração (variáveis no topo de cada script)

| Variável                          | Uso                                                    |
| --------------------------------- | ------------------------------------------------------ |
| `LOG_DIR`                         | diretório dos logs (padrão `/var/log/healthcheck`)     |
| `RETENTION_DAYS`                  | apaga logs mais antigos que N dias                     |
| `LIMITE_DISCO` / `LIMITE_MEM`     | limiares de alerta em %                                |
| `APACHE_SERVICE` / `APACHE_PORTS` | serviço e portas do Apache                             |
| `SPRING_PATTERN` / `SPRING_PORT`  | padrão do processo Java e porta (ajustar por ambiente) |
| `LISTENER_PORT` / `PMON_PATTERN`  | porta do listener e prefixo do processo pmon           |

`SPRING_PATTERN` é o campo que mais erra na prática — deve casar com o nome real do jar/app.

## Testar localmente

```bash
cd trabalho

# 1) Validar sintaxe (obrigatório antes de qualquer commit)
bash -n healthcheck_apache.sh && bash -n healthcheck_oracle.sh

# 2) Rodar sem tocar em /var/log (redireciona o LOG_DIR para /tmp)
sed 's#/var/log/healthcheck#/tmp/hc#' healthcheck_oracle.sh > /tmp/t.sh
bash /tmp/t.sh && cat /tmp/hc/oracle_*.log
```

Se houver `shellcheck` disponível, rode `shellcheck -S warning *.sh`.

## Deploy

```bash
sudo cp trabalho/healthcheck_apache.sh /usr/local/sbin/     # _oracle no servidor DB
sudo chmod 750 /usr/local/sbin/healthcheck_apache.sh
sudo mkdir -p /var/log/healthcheck
```

Cron (no crontab do root):

```
*/30 * * * * /usr/local/sbin/healthcheck_apache.sh
*/30 * * * * /usr/local/sbin/healthcheck_oracle.sh
```

## Convenções

- Um problema é sempre marcado com o prefixo `[ALERTA]` — é o token que a operação usa para triagem (`grep ALERTA`).
- Nome do log: `<serviço>_<host>_AAAAMMDD_HHMMSS.log`.
- Toda a saída do script vai para o arquivo de log (bloco `{ ... } >> "$LOG"`), nunca para o stdout do cron.
- Quando saudável, o script é silencioso: linhas `[ALERTA]` só aparecem quando há problema real (ex.: disco/inodes só imprimem se passarem do limite).

## Decisões técnicas (não regredir)

- **Detecção de porta** usa `ss -tln "sport = :$P" | grep -q LISTEN`, não `grep ":$P "`. Evita casar `80` com `8080` e é robusto entre versões de `ss`. Encapsulada na função `check_port()` (topo de cada script) — reutilizada para todas as portas checadas (Apache, Spring Batch, listener Oracle); ao adicionar uma nova porta, chame `check_port "$PORTA"` em vez de repetir o `ss`.
- **Detecção de instância Oracle** usa `ps -eo pid,args | awk '$2 ~ "^"pattern'`, ancorado no início do comando. Um `pgrep -f "ora_pmon_"` ingênuo casa com o próprio `sed`/`grep` do script (auto-match) e reporta SID falso.
- **`grep -v grep`** nas agregações de processo Oracle é intencional (remove o próprio grep do resultado).
- **Oracle só em nível SO** — decisão de escopo para não depender de ambiente Oracle nem travar o cron esperando login no banco. Checks de tablespace/sessão ficam fora deste repo. A "versão" do Oracle é aproximada pelo `ORACLE_HOME` listado em `/etc/oratab` (o path geralmente contém a versão, ex. `19.0.0/dbhome_1`), sem chamar `sqlplus`.
- **Agnóstico à versão** — não usar comandos exclusivos de uma versão de RHEL sem fallback. Gerenciador de pacotes, quando usado, deve detectar `dnf`/`yum`.
- **Detecção de versão de app** (`httpd -v`, `java -version`, `ORACLE_HOME`) é sempre informativa, nunca gera `[ALERTA]`, e só executa se o binário/arquivo existir (`command -v` / `[ -r ... ]`) — servidor sem o pacote não deve gerar ruído no log.
- **Resumo Capacity** (última seção do log, antes de `===== fim`): tabela alinhada (`printf "%-Ns ..."`) com `CPU_Qtd CPU_Uso CPU_Load RAM_Tot RAM_Livre RAM_Uso Fisico_Tot OS_Tot OS_Livre ASM_Tot ASM_Livre Zumbi`, inspirada no `old_capacity_script.sh`. Reaproveita variáveis já calculadas no tronco comum (`CPU_TOTAL`, `CPU_USO`, `MEM`, `PROC_ZUMBI`) em vez de recalcular. `CPU_Load` usa vírgula decimal (formato BR de planilha), igual ao script antigo. No `healthcheck_apache.sh`, `ASM_Tot`/`ASM_Livre` ficam fixos em `0` (servidor de aplicação não roda ASM); as colunas são mantidas apenas para compatibilizar layout com o log do Oracle. No `healthcheck_oracle.sh`, ASM é lido via `asmcmd lsdg -p` rodando como usuário `grid`/`oracle` (mesmo padrão do script antigo) — continua sendo nível de infraestrutura ASM, não uma query de banco via `sqlplus`.

## Como estender

Para adicionar uma checagem, insira um bloco dentro do `{ ... }`, antes do `echo "===== fim..."`, seguindo o padrão:

```bash
echo "--- Minha checagem ---"
<comando> && echo "OK: descricao" || echo "  [ALERTA] descricao do problema"
```

Mantenha o prefixo `[ALERTA]` para preservar a triagem por `grep`. Veja `SKILLS.md` para o catálogo completo e um template comentado.

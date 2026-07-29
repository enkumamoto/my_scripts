# SKILLS.md

Catálogo das checagens executadas pelos scripts e runbook de como interpretar cada alerta.

## Visão geral

| Script                  | Servidor | Checagens específicas                                                                          |
| ----------------------- | -------- | ---------------------------------------------------------------------------------------------- |
| `healthcheck_apache.sh` | App      | serviço `httpd`, portas 80/443, nº de workers, erros recentes, Spring Batch (processo + porta) |
| `healthcheck_oracle.sh` | Oracle   | instâncias (pmon), listener (tnslsnr), porta 1521, memória agregada Oracle                     |

Ambos coletam também: release do SO, uptime, carga/CPU, memória/swap, disco e inodes.

## Checagens comuns (nos dois scripts)

- **Sistema** — release do RHEL e uptime. Uptime baixo inesperado = reboot recente, investigar.
- **Carga / CPU** — CPUs e load 1/5/15 min. Load sustentado acima do nº de CPUs indica saturação.
- **Memória** — `[ALERTA]` se uso ≥ `LIMITE_MEM` (padrão 90%). Verifique swap junto: swap subindo com memória cheia = pressão real.
- **Disco** — `[ALERTA]` por filesystem ≥ `LIMITE_DISCO` (padrão 85%).
- **Inodes** — `[ALERTA]` se inodes ≥ limite. Disco "cheio" com espaço livre = quase sempre inodes esgotados (muitos arquivos pequenos).

## Runbook — o que cada alerta significa e a primeira ação

### `[ALERTA] memoria acima do limite`

Uso de RAM no limiar. Cheque `ps -eo pid,rss,comm --sort=-rss | head` para achar o maior consumidor. No servidor App, suspeite da JVM (heap mal dimensionado); no Oracle, é esperado consumo alto de SGA — reavalie o limiar se for o caso.

### `[ALERTA] disco <fs> em NN%`

Filesystem perto de encher. Ache os maiores diretórios: `du -xh /<fs> | sort -rh | head`. Atenção a logs de aplicação e arquivos de trace/audit do Oracle.

### `[ALERTA] inodes <fs> em NN%`

Muitos arquivos pequenos. Localize o diretório problemático: `for d in /*; do echo "$(find $d -xdev | wc -l) $d"; done | sort -rn | head`.

### `[ALERTA] servico httpd inativo`

Apache parado. `systemctl status httpd` e `journalctl -u httpd --since "1 hour ago"`. Tente `systemctl start httpd` após entender a causa.

### `[ALERTA] porta 80/443 sem LISTEN`

Serviço no ar mas sem escutar a porta (config, bind falho, firewall). Confirme com `ss -tlnp | grep httpd` e revise a config do vhost.

### `[ALERTA] Spring Batch nao encontrado`

Nenhum processo casou com `SPRING_PATTERN`. **Causa mais comum: o padrão não bate com o nome real do app** — confira com `ps -ef | grep java` e ajuste `SPRING_PATTERN`. Se o padrão está certo, o job/serviço realmente caiu.

### `[ALERTA] nenhum processo pmon encontrado`

Instância Oracle não está no ar. Confirme: `ps -ef | grep pmon`. Verifique se o `PMON_PATTERN` bate (padrão `ora_pmon_`).

### `[ALERTA] Listener (tnslsnr) inativo` / `porta 1521 sem LISTEN`

Listener caído — instância pode estar de pé mas inacessível por rede. `lsnrctl status` (como usuário Oracle) e revise o `listener.ora`.

## Comandos úteis do dia a dia

Scripts em `trabalho/`.

```bash
# Triagem rápida de todos os alertas
grep ALERTA /var/log/healthcheck/*.log

# Último relatório de um servidor
ls -t /var/log/healthcheck/apache_*.log | head -1 | xargs cat

# Só os alertas do último relatório
ls -t /var/log/healthcheck/oracle_*.log | head -1 | xargs grep ALERTA
```

## Capacity planning a partir dos logs (`capacity_apache.py`)

Ferramenta Python separada (roda na estação do analista, não no servidor RHEL) que consolida os logs `apache_<host>_<data>_<hora>.log` do `healthcheck_apache.sh` em uma planilha `.xlsx` de dimensionamento.

```bash
cd trabalho
pip install -r requirements.txt
python capacity_apache.py ./logs -o capacity.xlsx
```

- Le todos os `.log` de uma pasta (com subpastas, se `BUSCAR_SUBPASTAS`/`--recursivo`), extrai CPU, load, memória, disco/inodes, zumbis e status do httpd/Spring Batch via regex.
- Gera 2 abas: **Dados_Brutos** (uma linha por log, valores fixos) e **Dimensionamento** (avisos, resumo estatístico por fórmula viva sobre `Dados_Brutos` — média/mediana/mínimo/máximo/P90/P95/desvio — e sizing do servidor novo com parâmetros ajustáveis em amarelo: `--rps`, `--ms-por-req`, `--workers`, `--mb-worker`, `--crescimento`, `--headroom`).
- Não altera nem lê nada no servidor RHEL; só processa os logs já coletados. Se `httpd` estiver inativo nas amostras, o resultado é tratado como piso (SO + agentes), não como carga real de produção — a planilha avisa isso automaticamente.

## Interpretação do resultado do cron

Os scripts gravam tudo no log; não emitem stdout. Para disparar notificação, envolva a chamada em um wrapper que verifica `[ALERTA]` no log mais recente e só então alerta (e-mail, Slack, Zabbix). Assim o cron fica silencioso no caso saudável.

## Como adicionar uma nova checagem (skill)

Insira o bloco dentro do `{ ... }`, antes da linha `echo "===== fim..."`. Template comentado:

```bash
echo "--- <Nome da checagem> ---"

# Padrão OK/ALERTA: comando de sucesso à esquerda, alerta à direita.
<comando de verificacao> >/dev/null 2>&1 \
  && echo "<recurso>: OK" \
  || echo "  [ALERTA] <recurso> com problema"

# Padrão por limiar (imprime só quando estoura):
VALOR=$(<comando que devolve um numero>)
[ "$VALOR" -ge "<LIMITE>" ] && echo "  [ALERTA] <recurso> em ${VALOR}"
```

Regras ao estender:

- Sempre usar o prefixo `[ALERTA]` (a operação faz triagem por `grep ALERTA`).
- Nada de comando exclusivo de uma versão de RHEL sem fallback (o parque é misto 7/8/9).
- Testar com `bash -n` antes de subir.

Ideias de próximas skills: sincronia de horário (`chronyc tracking`), validade de certificado SSL do Apache, atualizações de segurança pendentes, espaço em `/var/log/audit`.

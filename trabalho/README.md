# trabalho/

Suíte de health check e capacity planning de servidores RHEL. Ver `../CLAUDE.md` para o contexto completo do repositório.

## Arquivos

| Arquivo                    | O que é                                                                                  |
| --------------------------- | ----------------------------------------------------------------------------------------- |
| `healthcheck_apache.sh`     | Health check de SO para servidor de aplicação (Apache/httpd + Spring Batch). Roda via cron. |
| `healthcheck_oracle.sh`     | Health check de SO para servidor de banco (Oracle DB, apenas nível SO). Roda via cron.      |
| `capacity_apache.py`        | Lê os logs do `healthcheck_apache.sh` e gera planilha `.xlsx` de capacity planning.         |
| `capacity_oracle.py`        | Lê os logs do `healthcheck_oracle.sh` e gera planilha `.xlsx` de capacity planning.         |
| `capacity_apache.xlsx`      | Planilha de exemplo/uso corrente gerada pelo `capacity_apache.py`.                          |
| `old_capacity_script.sh`    | Script legado que inspirou o bloco "Resumo Capacity" dos health checks atuais.              |
| `requirements.txt`          | Dependência Python (`openpyxl`) usada pelos dois scripts `capacity_*.py`.                   |

## Health checks (`healthcheck_apache.sh` / `healthcheck_oracle.sh`)

Scripts Bash autocontidos, sem dependências externas além de ferramentas base do RHEL (`awk`, `ss`, `df`, `free`, `pgrep`, `ps`, `systemctl`). Rodam como root via cron, gravam um log por execução em `/var/log/healthcheck` (configurável) e limpam logs antigos automaticamente.

```bash
# validar sintaxe antes de commitar
bash -n healthcheck_apache.sh && bash -n healthcheck_oracle.sh

# rodar localmente sem tocar em /var/log
sed 's#/var/log/healthcheck#/tmp/hc#' healthcheck_oracle.sh > /tmp/t.sh
bash /tmp/t.sh && cat /tmp/hc/oracle_*.log
```

Deploy:

```bash
sudo cp healthcheck_apache.sh /usr/local/sbin/     # _oracle no servidor DB
sudo chmod 750 /usr/local/sbin/healthcheck_apache.sh
sudo mkdir -p /var/log/healthcheck
```

Cron (crontab do root):

```
*/30 * * * * /usr/local/sbin/healthcheck_apache.sh
*/30 * * * * /usr/local/sbin/healthcheck_oracle.sh
```

Ambas as checagens seguem a mesma convenção: um problema é sempre marcado com o prefixo `[ALERTA]`, e o script fica silencioso quando o servidor está saudável.

## Capacity planning (`capacity_apache.py` / `capacity_oracle.py`)

Ferramentas Python que rodam na máquina do analista (não no servidor RHEL), leem os logs gerados pelo health check correspondente e geram uma planilha `.xlsx` com 2 abas:

- **Dados_Brutos** — uma linha por log, valores fixos extraídos diretamente do texto.
- **Dimensionamento** — avisos/premissas, resumo estatístico (fórmulas vivas sobre `Dados_Brutos`) e sizing do servidor novo, com parâmetros ajustáveis nas células amarelas.

Acrescentar logs novos em `Dados_Brutos` e reabrir a planilha recalcula tudo — as estatísticas não são valores fixos calculados em Python.

### Instalação

```bash
cd trabalho
python3 -m venv .venv && source .venv/bin/activate   # opcional, mas recomendado
pip install -r requirements.txt
```

### Uso

```bash
# Apache — usa PASTA_LOGS configurado no topo do arquivo
python capacity_apache.py
python capacity_apache.py ./logs -o capacity.xlsx
python capacity_apache.py ./logs --rps 250 --ms-por-req 22 --crescimento 2.0

# Oracle — mesma lógica, parâmetros de projeção diferentes (sem RPS/workers)
python capacity_oracle.py
python capacity_oracle.py ./logs -o capacity.xlsx
python capacity_oracle.py ./logs --crescimento 2.0 --headroom 0.3
```

Ajuste o bloco `CONFIGURACAO` no topo de cada arquivo (principalmente `PASTA_LOGS`) ou passe tudo por linha de comando.

**Rodando pelo botão Run do VSCode (macOS/Homebrew):** o Run usa o `python3` do sistema, não um `.venv`. Se aparecer `Erro: openpyxl nao instalado`, o Homebrew bloqueia `pip install` direto no Python gerenciado por ele (PEP 668). Instale assim:

```bash
/usr/bin/env python3 -m pip install --user --break-system-packages openpyxl
```

`--user` isola a instalação do site-packages do sistema, então o `--break-system-packages` é seguro aqui.

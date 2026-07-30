# meus_scripts

Utilitários de uso pessoal.

## comparar_e_colar.py

Compara recursivamente uma pasta de ORIGEM com uma pasta de BACKUP e copia para o backup os arquivos que estiverem faltando (mesmo caminho relativo). Ignora por padrão pastas/arquivos de sistema do Windows e macOS (`System Volume Information`, `.DS_Store`, `Thumbs.db`, etc.).

### Uso

```bash
python3 comparar_e_colar.py                       # usa os caminhos padrao e pergunta o modo
python3 comparar_e_colar.py ORIGEM BACKUP          # informa caminhos manualmente
python3 comparar_e_colar.py --modo comparar        # so compara, nao copia nada
python3 comparar_e_colar.py --modo copiar          # so copia os faltantes, sem relatorio
python3 comparar_e_colar.py --modo ambos           # compara e copia (com relatorio)
python3 comparar_e_colar.py --check-size           # tambem recopia se o tamanho diferir
python3 comparar_e_colar.py --incluir-tudo         # NAO ignora arquivos de sistema
```

Se `--modo` não for informado, o script pergunta interativamente (menu 1/2/3) o que fazer:

1. **comparar** — só mostra o relatório `[ALERTA]` dos arquivos faltantes, não copia nada.
2. **copiar** — copia os arquivos faltantes, sem imprimir o relatório detalhado.
3. **ambos** — mostra o relatório e copia (comportamento completo).

`--dry-run` sempre força "não copiar", independente do modo escolhido.

Caminhos padrão de origem/backup ficam nas constantes `ORIGEM_PADRAO` e `BACKUP_PADRAO` no topo do arquivo.

## formatar_hd_exfat.py

Detecta o(s) HD(s)/pendrive(s) **externo(s)** conectado(s) no macOS, pede confirmação e formata em exFAT (compatível com leitura/escrita em Windows, macOS e Linux).

**Atenção: formatar apaga todos os dados do disco escolhido — não há volta.**

### Uso

```bash
python3 formatar_hd_exfat.py                 # detecta o disco externo e pergunta
python3 formatar_hd_exfat.py "MEU_HD"        # idem, ja definindo o nome do volume
```

Funciona apenas no macOS (usa `diskutil`). Nunca formata disco marcado como interno — trava de segurança embutida. Pede duas confirmações antes de apagar (digitar `APAGAR` e depois `s`).

Esquema de partição escolhido automaticamente: MBR até 2TB, GPT acima disso.

Observação sobre permissões: exFAT não guarda o bit de execução Unix. Para tornar um arquivo executável em Linux/macOS após copiar, use `chmod +x nome_do_arquivo`.

## aws_cleanup.py

**Script destrutivo.** Remove permanentemente todos os recursos de uma conta AWS (EC2, RDS, S3, Lambda, IAM, VPC, etc.), em paralelo via `boto3`/`concurrent.futures`. Pensado para higienizar contas de sandbox/teste — nunca rodar contra uma conta de produção.

### Uso

```bash
python3 aws_cleanup.py --scan                          # so lista os recursos existentes, nao apaga nada
python3 aws_cleanup.py --dry-run                        # simula a limpeza completa sem apagar
python3 aws_cleanup.py --confirm                        # executa a limpeza de verdade (pede confirmacao)
python3 aws_cleanup.py --region us-east-1 --confirm      # regiao especifica
python3 aws_cleanup.py --services ec2,s3,rds --confirm   # limita a servicos especificos
python3 aws_cleanup.py --max-workers 5 --confirm         # paralelismo das chamadas AWS
```

Requer credenciais AWS configuradas (`~/.aws/credentials` ou variáveis de ambiente) com permissão para os serviços que for limpar. Cada execução grava um log de auditoria `aws_cleanup_log_AAAAMMDD_HHMMSS.json` com todas as ações tentadas, sucesso/falha e se foi `dry_run`.

## localiza_emove.py

Varre recursivamente uma pasta em busca de PDF/DOC/DOCX/XLS/XLSX, detecta arquivos repetidos por conteúdo (hash SHA-256) e organiza tudo dentro de uma pasta `Documentos`, em três subpastas: `DOCS` (.doc/.docx), `XLS` (.xls/.xlsx) e `PDFs` (.pdf). Também remove pastas vazias deixadas para trás na origem depois de mover os arquivos.

### Uso

```bash
python3 localiza_emove.py /caminho/da/origem                          # pergunta o que fazer (menu)
python3 localiza_emove.py /caminho/da/origem --dry-run                # so mostra o que faria
python3 localiza_emove.py /caminho/da/origem --documentos /outra/pasta/Documentos
python3 localiza_emove.py /caminho/da/origem --acao mover             # so localiza e move
python3 localiza_emove.py /caminho/da/origem --acao limpar            # so remove pastas vazias na origem
python3 localiza_emove.py /caminho/da/origem --acao tudo              # mover + limpar (padrao do menu)
```

Se `--acao` não for informado, o script pergunta interativamente (menu 1/2/3):

1. **tudo** — localiza, move e depois remove as pastas vazias que sobraram.
2. **mover** — só localiza e move, sem remover pastas.
3. **limpar** — só remove pastas vazias na origem, sem mover nada.

Regras de segurança: duplicatas (mesmo conteúdo) são movidas apenas uma vez, as cópias extras ficam onde estão; se já existir no destino um arquivo idêntico o arquivo de origem é apenas pulado (não sobrescreve, não duplica); se existir um arquivo diferente com o mesmo nome, o novo é renomeado (`nome_1.pdf`, `nome_2.pdf`...). A remoção de pastas vazias nunca apaga a pasta de origem em si nem as pastas de destino (`DOCS`/`XLS`/`PDFs`).

## battery_health.sh

Diagnóstico de saúde da bateria em notebooks **Linux**, lendo `/sys/class/power_supply`. Mostra status de carga, percentual atual, saúde estimada (`energy_full` / `energy_full_design`) e ciclos de carga, com interpretação textual dos resultados.

### Uso

```bash
bash battery_health.sh
```

Não recebe argumentos. Precisa de `bc` instalado (usado para o cálculo percentual de saúde). Sem efeito em macOS/Windows — depende da interface `/sys/class/power_supply` do kernel Linux.

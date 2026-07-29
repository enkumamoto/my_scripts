# meus_scripts

Utilitários pessoais soltos, sem relação com a suíte `oraex/` (health check Oracle/Apache). São dois scripts Python independentes.

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

# SKILLS.md

Catálogo das regras checadas pelo `git_check` e runbook de como interpretar cada pendência e cada erro da API. Vale só para esta pasta; o `SKILLS.md` da raiz trata da suíte de health check.

## Visão geral

| Seção da página | O que mostra | Ações |
| --- | --- | --- |
| Públicos | 9 regras por repositório + nota (`ok`/total) | Tornar privado |
| Privados | linguagem e último push (sem regras) | Tornar público |
| Menu lateral | contagem de públicos com cada pendência | corrige em lote, um repo por chamada |

Estados: `✓ ok`, `✗ falha` (pendência), `? nd` (a API não informou — geralmente falta permissão de admin ou o repositório está vazio). Passe o mouse na etiqueta para ver o detalhe.

## Catálogo de regras (repositórios públicos)

| Regra | Como é checada | Falha significa | Correção |
| --- | --- | --- | --- |
| Descricao | campo `description` de `GET /repos/{r}` | repo sem descrição | menu → Adicionar Descrição |
| README | `files.readme` de `GET /repos/{r}/community/profile` | GitHub não reconhece README | menu → Adicionar README.md |
| Licenca | `files.license` do community profile | sem `LICENSE` reconhecido | menu → Adicionar Licença |
| .gitignore | `GET /repos/{r}/contents/.gitignore` (200/404) | sem `.gitignore` na raiz | menu → Adicionar .gitignore |
| Branch protegida | proteção clássica (`/branches/{b}/protection`) **ou** ruleset ativo (`/rules/branches/{b}`) na branch padrão | branch padrão sem nenhuma proteção | menu → Adicionar regras (ruleset de `Pull_Requests-2.json`) |
| Sem force push | regra `non_fast_forward` no ruleset ou `allow_force_pushes.enabled = false` na proteção clássica | force push liberado na branch padrão | menu → Adicionar regras |
| Secret scanning | `security_and_analysis.secret_scanning.status` | escaneamento de segredos desligado | menu → Adicionar regras |
| Push protection | `security_and_analysis.secret_scanning_push_protection.status` | push com segredo não é bloqueado | menu → Adicionar regras |
| Dependabot | `GET /repos/{r}/vulnerability-alerts` (204 = ligado, 404 = desligado) | alertas de dependência vulnerável desligados | menu → Ativar alertas do Dependabot |

Observações:

- README e licença dependem do *community profile*, que o GitHub atualiza com atraso: após o commit a etiqueta pode ficar `✗` por alguns minutos. Clique em "Recarregar" depois.
- Repo **vazio** (sem commits): branch, `.gitignore` e community profile costumam vir como `✗`/`?`. Adicionar o README pelo menu cria o primeiro commit.
- Repositórios privados não são checados nem recebem regras — por decisão de escopo.

## Runbook — erros que aparecem na página

### `token da pagina invalido; recarregue a pagina` (403)

O servidor foi reiniciado e a aba ainda tem o token da execução anterior. Recarregue a página (F5).

### `Invalid host header` (400)

Acesso por um host que não é `127.0.0.1`/`localhost` (ex.: IP da rede ou outro nome). Use `http://127.0.0.1:<porta>`.

### `Bad credentials` (401)

Token do GitHub inválido ou expirado. Rode `gh auth status`; se preciso `gh auth login` (ou ajuste `GITHUB_TOKEN`) e reinicie o script.

### `API rate limit exceeded` (403)

Limite de 5000 chamadas/h estourado (cada carregamento gasta ~6 chamadas por repo público). Veja quando reseta: `gh api rate_limit --jq .resources.core`.

### `<arquivo> ja existe no repositorio` (409)

Proteção contra sobrescrita: o `.gitignore`/`README.md`/`LICENSE` já está lá. Se a etiqueta ainda mostra `✗`, o GitHub pode não reconhecer o arquivo (ex.: README com outro nome/extensão, licença em formato não padrão) — corrija manualmente no repo.

### `branch padrao exige PR: aberto o #N`

Não é erro: o ruleset da branch padrão bloqueou o commit direto, então o arquivo foi para a branch `git-check/<arquivo>` e um PR foi aberto. Faça o merge pelo link. Se a branch `git-check/...` já existir de uma tentativa anterior, a criação falha com `Reference already exists` — apague a branch ou faça merge do PR antigo.

### `Name must be unique` / erro 422 ao criar ruleset

Já existe um ruleset com o mesmo `name` do `Pull_Requests-2.json` no repositório. Normalmente o painel nem tenta (só aplica onde a branch está sem proteção); se ocorrer, revise os rulesets em Settings → Rules.

### `nao foi possivel ler Pull_Requests-2.json` / `... invalido` (500)

O JSON do ruleset está ausente ou malformado; a opção do ruleset aparece desabilitada no diálogo. Corrija o arquivo (precisa ter `name` e `rules`) ou exporte de novo pelo GitHub: Settings → Rules → Rulesets → … → Export. Clique em "Recarregar".

### `repositorio privado nao recebe regras` (422)

Tentativa de aplicar regras em repositório privado — bloqueado por decisão de escopo.

### Página não se atualiza depois de salvar o código

- Veja o terminal: erro de sintaxe/import aparece como traceback e o servidor fica sem responder até você corrigir e salvar de novo.
- O script foi iniciado com `--sem-recarga`? Então reinicie na mão (a página recarrega sozinha quando o servidor volta).
- `Erro: dependencia nao instalada (watchfiles)`: rode `pip install -r requirements.txt` de novo.
- Mudanças só no `Pull_Requests-2.json` não reiniciam o servidor — clique em "Recarregar".

### `Repository was archived so is read-only` (403)

Repo arquivado não aceita mudanças. Desarquive em Settings → Danger Zone, aplique e arquive de novo se quiser.

### Etiqueta `?` em Secret scanning / Push protection

A API só devolve `security_and_analysis` para quem é admin. Confira se o token é do dono do repo.

### Troca de visibilidade recusada

- **Fork:** botão desabilitado — o GitHub não permite mudar visibilidade de fork.
- **Organização:** a org pode proibir membros de mudar visibilidade (política da org).
- Tornar **público** expõe todo o histórico; tornar **privado** perde stars/watchers e desvincula forks públicos.

## Comandos úteis (`gh`) para conferir à mão

```bash
R=enkumamoto/<repo>
gh api repos/$R --jq '{private, description, default_branch, security_and_analysis}'
gh api repos/$R/community/profile --jq '.files | {readme, license}'
gh api repos/$R/rulesets --jq '.[] | {id, name, enforcement}'
gh api repos/$R/rules/branches/main --jq '[.[].type]'
gh api repos/$R/vulnerability-alerts -i 2>&1 | head -1     # 204 ligado, 404 desligado

# exportar o ruleset de um repo para usar como Pull_Requests-2.json
gh api repos/$R/rulesets/<id> > Pull_Requests-2.json
```

## Como adicionar uma nova regra ou ação

Ver a seção "Como estender" do `CLAUDE.md` desta pasta. Ao criar uma regra nova, acrescente uma linha no catálogo acima (como é checada, o que significa falha, como corrigir) e, se houver erro novo previsível, uma entrada no runbook.

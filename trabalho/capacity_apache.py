#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
capacity_apache.py — Analise de capacity a partir dos logs de health check Apache.

Le os arquivos apache_<host>_<data>_<hora>.log gerados pelo script de health check,
extrai as metricas de cada coleta e gera uma planilha .xlsx com 2 abas:

    Dados_Brutos       uma linha por log (valores fixos, sem calculo)
    Dimensionamento    premissas/avisos + resumo estatistico (formulas vivas) +
                        sizing do servidor novo, com parametros ajustaveis

Todas as estatisticas sao FORMULAS, nao valores calculados em Python: ao acrescentar
novas coletas em Dados_Brutos (ate a linha 200) a planilha se atualiza sozinha.

Uso:
    1) Abra este arquivo, ajuste o bloco CONFIGURACAO logo abaixo dos imports
       (principalmente PASTA_LOGS) e rode sem argumentos:

           python capacity_apache.py

    2) Ou passe tudo por linha de comando, o que sobrescreve a configuracao:

           python capacity_apache.py D:\\logs\\apache -o capacity.xlsx
           python capacity_apache.py ./logs --rps 250 --ms-por-req 22 --crescimento 2.0
           python capacity_apache.py ./logs --host GNCASNHL00294

Requisito: openpyxl  (pip install openpyxl)
"""

import argparse
import glob
import os
import re
import sys
from collections import OrderedDict

try:
    from openpyxl import Workbook
    from openpyxl.comments import Comment
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.utils import get_column_letter
except ImportError:
    sys.exit("Erro: openpyxl nao instalado.  ->  pip install openpyxl")


# #####################################################################
#                          C O N F I G U R A C A O
#          Ajuste os valores abaixo. Nada mais precisa ser alterado.
# #####################################################################

# ---------------------------------------------------------------------
# Pasta onde os logs importados do host sao depositados.
# Use r'...' (string crua) para caminhos Windows, senao a barra invertida
# e interpretada como caractere de escape.
#
#   Windows local ....: r'C:\logs\apache'
#   Windows em rede ..: r'\\servidor\compartilhamento\logs\apache'
#   Linux / Unix .....: '/opt/logs/apache'
#   Pasta do script ..: '.'
# ---------------------------------------------------------------------
PASTA_LOGS = r'/Users/ronin/Documents/apache'

# Arquivo .xlsx gerado. Caminho relativo cai na pasta de onde o script rodou.
ARQUIVO_SAIDA = 'capacity_apache.xlsx'

# Varrer tambem as subpastas de PASTA_LOGS?
# True  = util quando os logs chegam organizados por data ou por host
# False = le apenas os .log soltos na pasta indicada
BUSCAR_SUBPASTAS = True

# Processar apenas um host especifico. Deixe None para consolidar todos
# os hosts encontrados na pasta.  Ex.: 'GNCASNHL00294'
HOST = None

# ---------------------------------------------------------------------
# Parametros de projecao. Viram os valores iniciais das celulas amarelas
# da aba Dimensionamento e podem ser reajustados dentro da planilha.
# ---------------------------------------------------------------------
RPS_ESPERADO   = 120    # requisicoes por segundo esperadas no pico
MS_POR_REQ     = 15     # CPU consumida por requisicao, em milissegundos
MAX_WORKERS    = 256    # MaxRequestWorkers previsto no httpd.conf
MB_POR_WORKER  = 25     # RAM media por worker httpd, em MB
FATOR_CRESC    = 1.5    # crescimento no horizonte de vida do servidor
HEADROOM       = 0.30   # folga alvo em pico (0.30 = manter 30% livre)

# #####################################################################
#                     FIM DA CONFIGURACAO
# #####################################################################


# =====================================================================
# 1. PARSING DOS LOGS
# =====================================================================

RE_CAB    = re.compile(r'HEALTH CHECK APACHE\s*[-—]\s*(\S+)\s*[-—]\s*(\d{4}-\d{2}-\d{2})\s+(\d{2}:\d{2}:\d{2})')
RE_SO     = re.compile(r'^(Red Hat.*|CentOS.*|Oracle Linux.*|Ubuntu.*|SUSE.*)$', re.M)
RE_UPTIME = re.compile(r'Uptime:\s*(.+)')
RE_CPU    = re.compile(r'CPUs:\s*(\d+)\s*\|\s*Load\(1/5/15\):\s*([\d.,]+),\s*([\d.,]+),\s*([\d.,]+)')
RE_CPUPCT = re.compile(r'Uso de CPU \(load1/CPUs\):\s*(\d+)%')
RE_MEM    = re.compile(r'Memoria:\s*(\d+)MB usados de (\d+)MB total \((\d+)%')
RE_DISCO  = re.compile(r'^\s*(\d+)%\s+usado:(\S+)\s+total:(\S+)\s+(\S+)\s*$', re.M)
RE_PROC   = re.compile(r'Processos em execucao:\s*(\d+)')
RE_ZUMBI  = re.compile(r'Processos zumbis:\s*(\d+)')
RE_HTTPD  = re.compile(r'Processos httpd em execucao:\s*(\d+)')
RE_JAVA   = re.compile(r'Versao Java:\s*(\S+)')

MULT = {'K': 1 / 1024 ** 2, 'M': 1 / 1024, 'G': 1.0, 'T': 1024.0, 'P': 1024.0 ** 2}


def para_gb(txt):
    """Converte '19G', '500M', '1.5T' em GB (float). Retorna None se nao reconhecer."""
    m = re.match(r'^([\d.,]+)\s*([KMGTP])i?B?$', str(txt).strip(), re.I)
    if not m:
        return None
    return float(m.group(1).replace(',', '.')) * MULT[m.group(2).upper()]


def num(txt):
    """Converte '0,52' ou '0.52' em float."""
    return float(str(txt).replace(',', '.'))


def parse_log(texto, arquivo):
    """Extrai as metricas de um log. Retorna dict, ou None se o cabecalho nao bater."""
    cab = RE_CAB.search(texto)
    if not cab:
        return None

    r = OrderedDict()
    r['arquivo'] = arquivo
    r['host'], r['data'], r['hora'] = cab.group(1), cab.group(2), cab.group(3)

    m = RE_SO.search(texto)
    r['so'] = m.group(1).strip() if m else ''
    m = RE_UPTIME.search(texto)
    r['uptime'] = m.group(1).strip() if m else ''
    m = RE_JAVA.search(texto)
    r['java'] = m.group(1) if m else ''

    m = RE_CPU.search(texto)
    if m:
        r['cpus']   = int(m.group(1))
        r['load1']  = num(m.group(2))
        r['load5']  = num(m.group(3))
        r['load15'] = num(m.group(4))
    else:
        r['cpus'] = r['load1'] = r['load5'] = r['load15'] = None

    m = RE_CPUPCT.search(texto)
    r['cpu_pct'] = int(m.group(1)) if m else None

    m = RE_MEM.search(texto)
    if m:
        r['mem_mb'], r['mem_tot_mb'], r['mem_pct'] = int(m.group(1)), int(m.group(2)), int(m.group(3))
    else:
        r['mem_mb'] = r['mem_tot_mb'] = r['mem_pct'] = None

    # discos: chave dinamica por ponto de montagem
    r['_discos'] = {}
    for d in RE_DISCO.finditer(texto):
        pct, usado, total, mnt = int(d.group(1)), d.group(2), d.group(3), d.group(4)
        r['_discos'][mnt] = {'pct': pct, 'usado_gb': para_gb(usado), 'total_gb': para_gb(total)}

    for regex, chave in ((RE_PROC, 'procs'), (RE_ZUMBI, 'zumbis'), (RE_HTTPD, 'httpd_procs')):
        m = regex.search(texto)
        r[chave] = int(m.group(1)) if m else None

    # flags de servico: o script de health check imprime [ALERTA] quando esta fora
    r['httpd_ativo'] = 0 if 'servico httpd inativo' in texto else 1
    r['porta80']     = 0 if 'porta 80 sem LISTEN'   in texto else 1
    r['porta443']    = 0 if 'porta 443 sem LISTEN'  in texto else 1
    r['porta8080']   = 0 if 'porta 8080 sem LISTEN' in texto else 1
    r['batch_ok']    = 0 if 'Spring Batch nao encontrado' in texto else 1
    return r


def coletar(entradas, host_filtro=None, recursivo=False):
    """Recebe diretorios, arquivos ou padroes glob. Devolve (registros, ignorados)."""
    caminhos = []
    for e in entradas:
        if os.path.isdir(e):
            if recursivo:
                caminhos += glob.glob(os.path.join(e, '**', '*.log'), recursive=True)
            else:
                caminhos += glob.glob(os.path.join(e, '*.log'))
        elif os.path.isfile(e):
            caminhos.append(e)
        else:
            caminhos += glob.glob(e)

    registros, ignorados = [], []
    for p in sorted(set(caminhos)):
        try:
            with open(p, encoding='utf-8', errors='replace') as f:
                texto = f.read()
        except OSError as ex:
            ignorados.append((os.path.basename(p), str(ex)))
            continue
        reg = parse_log(texto, os.path.basename(p))
        if reg is None:
            ignorados.append((os.path.basename(p), 'cabecalho HEALTH CHECK nao encontrado'))
            continue
        if host_filtro and reg['host'] != host_filtro:
            continue
        registros.append(reg)

    registros.sort(key=lambda x: (x['data'], x['hora']))
    return registros, ignorados


# =====================================================================
# 2. ESTILOS
# =====================================================================

FONTE = 'Arial'
H1   = Font(name=FONTE, size=14, bold=True, color='FFFFFF')
H2   = Font(name=FONTE, size=11, bold=True, color='FFFFFF')
SEC  = Font(name=FONTE, size=11, bold=True, color='1F3864')
BD   = Font(name=FONTE, size=10, bold=True)
NM   = Font(name=FONTE, size=10)
INP  = Font(name=FONTE, size=10, color='0000FF')     # valor fixo / entrada
LNK  = Font(name=FONTE, size=10, color='008000')     # referencia a outra aba
SM   = Font(name=FONTE, size=9, italic=True, color='595959')
WARN = Font(name=FONTE, size=10, bold=True, color='C00000')
DEST = Font(name=FONTE, size=12, bold=True, color='1F3864')
FINAL= Font(name=FONTE, size=12, bold=True, color='C00000')

F_H   = PatternFill('solid', fgColor='1F3864')
F_H2  = PatternFill('solid', fgColor='2E5C9A')
F_IN  = PatternFill('solid', fgColor='FFFF00')       # celula a preencher
F_ZEB = PatternFill('solid', fgColor='F2F2F2')
F_AL  = PatternFill('solid', fgColor='FCE4E4')

_thin = Side(style='thin', color='BFBFBF')
BOX = Border(left=_thin, right=_thin, top=_thin, bottom=_thin)

LINHA_LIMITE = 200   # ate onde as formulas de Dimensionamento enxergam Dados_Brutos
NOTA_COL = 12        # coluna L: notas das linhas de parametro/resultado em Dimensionamento


# =====================================================================
# 3. GERACAO DA PLANILHA
# =====================================================================

def _bloco(ws, r, titulo, col_fim=10):
    c = ws.cell(r, 2, titulo)
    c.font, c.fill = H2, F_H2
    ws.merge_cells(start_row=r, start_column=2, end_row=r, end_column=col_fim)
    return r + 1


def _linha(ws, r, rotulo, valor, fmt, nota, tipo='calc'):
    """Escreve rotulo | valor | nota (coluna L). tipo: calc | input | link."""
    ws.cell(r, 2, rotulo).font = BD
    c = ws.cell(r, 3, valor)
    c.number_format, c.border = fmt, BOX
    c.alignment = Alignment(horizontal='center')
    if tipo == 'input':
        c.font, c.fill = INP, F_IN
    elif tipo == 'link':
        c.font = LNK
    else:
        c.font = NM
    n = ws.cell(r, NOTA_COL, nota)
    n.font = SM
    n.alignment = Alignment(wrap_text=True, vertical='center')
    return r + 1


def _texto(ws, r, rotulo, texto, rotulo_font=BD, texto_font=NM, altura=None):
    """Escreve rotulo em B e um texto livre mesclado de C ate L (wrap)."""
    ws.cell(r, 2, rotulo).font = rotulo_font
    c = ws.cell(r, 3, texto)
    c.font = texto_font
    c.alignment = Alignment(wrap_text=True, vertical='top')
    ws.merge_cells(start_row=r, start_column=3, end_row=r, end_column=NOTA_COL)
    if altura:
        ws.row_dimensions[r].height = altura
    return r + 1


def gerar_planilha(regs, ignorados, params, destino):
    n = len(regs)
    hosts = sorted({r['host'] for r in regs})
    # pontos de montagem presentes em qualquer log, com / sempre primeiro
    mounts = sorted({m for r in regs for m in r['_discos']},
                    key=lambda x: (x != '/', x))

    wb = Workbook()

    # -------- ABA 1: DADOS BRUTOS ---------------------------------
    wd = wb.active
    wd.title = 'Dados_Brutos'
    wd.sheet_view.showGridLines = False

    cols = [('Arquivo', 'arquivo', 42, None), ('Host', 'host', 18, None),
            ('Data', 'data', 11, None), ('Hora', 'hora', 10, None),
            ('CPUs', 'cpus', 7, '0'), ('CPU Uso (%)', 'cpu_pct', 11, '0'),
            ('Load 1min', 'load1', 10, '0.00'), ('Load 5min', 'load5', 10, '0.00'),
            ('Load 15min', 'load15', 11, '0.00'),
            ('Mem Usada (MB)', 'mem_mb', 14, '#,##0'),
            ('Mem Total (MB)', 'mem_tot_mb', 14, '#,##0'),
            ('Mem Uso (%)', 'mem_pct', 11, '0')]
    for mnt in mounts:
        cols.append((f'Disco {mnt} (%)', f'disco::{mnt}', 13, '0'))
    cols += [('Processos', 'procs', 11, '0'), ('Zumbis', 'zumbis', 8, '0'),
             ('httpd Ativo (1/0)', 'httpd_ativo', 15, '0'), ('Proc httpd', 'httpd_procs', 11, '0'),
             ('Porta 80 (1/0)', 'porta80', 13, '0'), ('Porta 443 (1/0)', 'porta443', 14, '0'),
             ('Porta 8080 (1/0)', 'porta8080', 15, '0')]

    wd['A1'] = 'DADOS BRUTOS — uma linha por arquivo de log'
    wd['A1'].font, wd['A1'].fill = H1, F_H
    wd.merge_cells(start_row=1, start_column=1, end_row=1, end_column=len(cols))
    wd.row_dimensions[1].height = 24
    wd['A2'] = ('Valores extraidos diretamente dos logs, sem calculo. Para novas coletas cole as linhas a partir '
                f'da primeira linha vazia — as formulas da aba Dimensionamento ja cobrem ate a linha {LINHA_LIMITE}.')
    wd['A2'].font = SM
    wd.merge_cells(start_row=2, start_column=1, end_row=2, end_column=len(cols))

    HDR = 3
    for i, (titulo, _, larg, _f) in enumerate(cols, start=1):
        c = wd.cell(HDR, i, titulo)
        c.font, c.fill, c.border = H2, F_H2, BOX
        c.alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)
        wd.column_dimensions[get_column_letter(i)].width = larg
    wd.row_dimensions[HDR].height = 30
    wd.freeze_panes = f'E{HDR + 1}'

    for j, reg in enumerate(regs):
        rr = HDR + 1 + j
        for i, (_t, chave, _l, fmt) in enumerate(cols, start=1):
            if chave.startswith('disco::'):
                d = reg['_discos'].get(chave.split('::', 1)[1])
                v = d['pct'] if d else None
            else:
                v = reg.get(chave)
            c = wd.cell(rr, i, v)
            c.font, c.border = INP, BOX
            if fmt:
                c.number_format = fmt
            c.alignment = Alignment(horizontal='center' if i > 4 else 'left')
            if j % 2:
                c.fill = F_ZEB
        if reg['httpd_ativo'] == 0:
            ic = [i for i, c_ in enumerate(cols, start=1) if c_[1] == 'httpd_ativo'][0]
            wd.cell(rr, ic).fill = F_AL
            wd.cell(rr, ic).font = WARN

    L1, LN = HDR + 1, HDR + n
    nota = wd.cell(LN + 2, 1, f'Fim dos dados importados: {n} amostras (linhas {L1} a {LN}). '
                              'Vermelho na coluna "httpd Ativo" = Apache parado no momento da coleta.')
    nota.font = SM
    wd.merge_cells(start_row=LN + 2, start_column=1, end_row=LN + 2, end_column=len(cols))

    def rng(chave):
        """Intervalo absoluto da coluna em Dados_Brutos, ate LINHA_LIMITE."""
        idx = [i for i, c_ in enumerate(cols, start=1) if c_[1] == chave][0]
        L = get_column_letter(idx)
        return f'Dados_Brutos!${L}${L1}:${L}${LINHA_LIMITE}'

    # -------- ABA 2: DIMENSIONAMENTO -------------------------------
    wm = wb.create_sheet('Dimensionamento')
    wm.sheet_view.showGridLines = False
    for cl, w in [('A', 3), ('B', 40), ('C', 14), ('D', 11), ('E', 11), ('F', 11),
                  ('G', 11), ('H', 11), ('I', 11), ('J', 62), ('K', 3), ('L', 62)]:
        wm.column_dimensions[cl].width = w

    wm['B1'] = 'CAPACITY PLANNING — SERVIDOR APACHE'
    wm['B1'].font, wm['B1'].fill = H1, F_H
    wm.merge_cells('B1:L1')
    wm.row_dimensions[1].height = 26

    pct_ativo = sum(r['httpd_ativo'] for r in regs) / n if n else 0
    janela = f"{regs[0]['data']} {regs[0]['hora']}  ate  {regs[-1]['data']} {regs[-1]['hora']}" if n else '-'

    r = 3
    for k, v in [('Host(s) de origem',   ', '.join(hosts)),
                 ('Sistema operacional', regs[0]['so'] if n else '-'),
                 ('Java',                regs[0]['java'] if n else '-'),
                 ('Amostras coletadas',  f'{n} logs'),
                 ('Janela',              janela),
                 ('Arquivos ignorados',  str(len(ignorados)) if ignorados else 'nenhum'),
                 ('Origem dos dados',    'Logs de health check gerados por script (apache_<host>_<data>_<hora>.log)')]:
        r = _texto(wm, r, k, v)

    r += 1
    wm.cell(r, 2, 'LEIA ANTES DE USAR OS NUMEROS').font = Font(name=FONTE, size=12, bold=True, color='C00000')
    wm.cell(r, 2).fill = F_AL
    wm.merge_cells(start_row=r, start_column=2, end_row=r, end_column=3)
    r += 1

    avisos = []
    if pct_ativo < 1:
        avisos.append((
            f'1. Apache fora do ar em {(1-pct_ativo)*100:.0f}% das amostras',
            f'Em {n - sum(x["httpd_ativo"] for x in regs)} das {n} coletas o httpd esta inativo. A media medida '
            'representa o servidor OCIOSO (SO + agentes), NAO um Apache atendendo trafego. Use a baseline como '
            'PISO e some por cima a carga estimada do Apache mais abaixo, na secao de dimensionamento.'))
    avisos.append((
        '2. Janela de amostragem',
        f'{n} pontos entre {janela}. Confirme se a janela cobre pico, fechamento, backup e batch. '
        'Recomendado 7 a 30 dias antes de fechar o sizing.'))
    discos_alerta = sorted({m for x in regs for m, d in x['_discos'].items() if d['pct'] >= 85})
    if discos_alerta:
        avisos.append((
            '3. Particao em alerta',
            'Ponto(s) de montagem acima de 85% em pelo menos uma coleta: ' + ', '.join(discos_alerta) +
            '. Problema atual do servidor de origem e licao direta para o dimensionamento do novo.'))
    if any(x['batch_ok'] == 0 for x in regs):
        avisos.append((
            '4. Spring Batch ausente',
            'O check nao encontrou o processo Spring Batch. Se o servidor novo tambem for hospeda-lo, '
            'esse consumo NAO esta representado em nenhum numero desta planilha.'))

    for k, v in avisos:
        r = _texto(wm, r, k, v, rotulo_font=WARN, altura=34)

    r += 1
    wm.cell(r, 2, 'COMO USAR').font = Font(name=FONTE, size=12, bold=True, color='1F3864')
    r += 1
    for k, v in [
        ('Dados_Brutos', 'Uma linha por log, valores fixos. Para incluir novas coletas acrescente linhas abaixo '
                         f'da ultima; as formulas abaixo ja cobrem ate a linha {LINHA_LIMITE}.'),
        ('Resumo (nesta aba)', 'Estatisticas por formula — atualizam sozinhas quando voce adiciona linhas em Dados_Brutos.'),
        ('Sizing (nesta aba)', 'Dimensionamento do servidor novo. Celulas AMARELAS sao os parametros ajustaveis.')]:
        r = _texto(wm, r, k, v, altura=28)

    r += 1
    wm.cell(r, 2, 'LEGENDA DE CORES').font = SEC
    r += 1
    for txt, fnt, fl in [('Valor fixo extraido do log', INP, None),
                         ('Celula para voce ajustar', NM, F_IN),
                         ('Resultado de formula', NM, None),
                         ('Referencia a outra secao', LNK, None)]:
        c = wm.cell(r, 2, '   exemplo'); c.font = fnt; c.border = BOX
        if fl:
            c.fill = fl
        wm.cell(r, 3, txt).font = NM
        r += 1

    if ignorados:
        r += 1
        wm.cell(r, 2, 'ARQUIVOS IGNORADOS').font = SEC
        r += 1
        for nome, motivo in ignorados:
            wm.cell(r, 2, nome).font = NM
            wm.cell(r, 3, motivo).font = SM
            r += 1

    # -------- 0. RESUMO DE CAPACITY (formulas sobre Dados_Brutos) --
    r += 1
    r = _bloco(wm, r, '0. RESUMO DE CAPACITY — estatisticas calculadas')
    wm.cell(r, 2, 'Tudo abaixo e formula sobre Dados_Brutos. Adicione linhas la e estes numeros se atualizam.').font = SM
    wm.merge_cells(start_row=r, start_column=2, end_row=r, end_column=10)
    r += 1

    wm.cell(r, 2, 'Amostras validas');          wm.cell(r, 2).font = BD
    wm.cell(r, 3, f'=COUNT({rng("cpu_pct")})'); wm.cell(r, 3).font = NM; wm.cell(r, 3).number_format = '0'
    wm.cell(r, 4, 'Amostras com httpd ATIVO');  wm.cell(r, 4).font = BD
    wm.cell(r, 6, f'=SUM({rng("httpd_ativo")})'); wm.cell(r, 6).font = NM; wm.cell(r, 6).number_format = '0'
    wm.cell(r, 7, '% do tempo no ar');          wm.cell(r, 7).font = BD
    wm.cell(r, 9, '=IFERROR(F{0}/C{0},0)'.format(r)); wm.cell(r, 9).font = NM; wm.cell(r, 9).number_format = '0.0%'
    r += 2

    HDR2 = r
    for i, t in enumerate(['Metrica', 'Media', 'Mediana', 'Minimo', 'Maximo',
                           'P90', 'P95', 'Desvio', 'Observacao']):
        c = wm.cell(HDR2, 2 + i, t)
        c.font, c.fill, c.border = H2, F_H2, BOX
        c.alignment = Alignment(horizontal='center', vertical='center')
    wm.row_dimensions[HDR2].height = 20
    r = HDR2 + 1

    metricas = [
        ('CPU Uso (%)',        'cpu_pct',    '0.0',   'Calculado pelo script como load1/CPUs.'),
        ('Load 1 min',         'load1',      '0.00',  'Absoluto: numero de nucleos ocupados.'),
        ('Load 5 min',         'load5',      '0.00',  'Menos ruidoso que o load1 para tendencia.'),
        ('Load 15 min',        'load15',     '0.00',  'Melhor indicador de carga sustentada.'),
        ('Memoria Usada (MB)', 'mem_mb',     '#,##0', 'Consumo real de SO + agentes.'),
        ('Memoria Uso (%)',    'mem_pct',    '0.0',   'Limite de alerta do script de health check: 90%.'),
    ]
    for mnt in mounts:
        metricas.append((f'Disco {mnt} (%)', f'disco::{mnt}', '0.0', 'Ocupacao do ponto de montagem.'))
    metricas += [
        ('Processos ativos',  'procs',       '0', 'Total do SO, nao apenas do Apache.'),
        ('Processos zumbis',  'zumbis',      '0', 'Acima de zero indica processo pai com problema.'),
        ('Processos httpd',   'httpd_procs', '0', 'Workers Apache no momento da coleta.'),
    ]

    lin_metrica = {}
    for nome, chave, fmt, obs in metricas:
        R = rng(chave)
        wm.cell(r, 2, nome).font = BD
        for i, f_ in enumerate([
                f'=IFERROR(AVERAGE({R}),"")', f'=IFERROR(MEDIAN({R}),"")',
                f'=IFERROR(MIN({R}),"")',     f'=IFERROR(MAX({R}),"")',
                f'=IFERROR(PERCENTILE({R},0.9),"")', f'=IFERROR(PERCENTILE({R},0.95),"")',
                f'=IFERROR(STDEV({R}),"")']):
            c = wm.cell(r, 3 + i, f_)
            c.font, c.border, c.number_format = NM, BOX, fmt
            c.alignment = Alignment(horizontal='center')
        wm.cell(r, 10, obs).font = SM
        for cc in range(2, 11):
            wm.cell(r, cc).border = BOX
        if chave.startswith('disco::') and any(
                x['_discos'].get(chave.split('::', 1)[1], {}).get('pct', 0) >= 85 for x in regs):
            for cc in range(2, 10):
                wm.cell(r, cc).fill = F_AL
        lin_metrica[chave] = r
        r += 1

    r += 1
    wm.cell(r, 2, 'CONVERSOES UTEIS').font = SEC
    r += 1
    base = r
    conversoes = [
        ('vCPU medias consumidas',        f'=C{lin_metrica["load1"]}', '0.00',
         'Load 1min medio = nucleos ocupados em media.'),
        ('vCPU consumidas no P95',        f'=H{lin_metrica["load1"]}', '0.00',
         'Pico observado na janela amostrada.'),
        ('vCPU provisionadas hoje',       f'=IFERROR(AVERAGE({rng("cpus")}),"")', '0',
         'Configuracao do servidor de origem.'),
        ('Taxa de utilizacao de CPU',     f'=IFERROR(C{base}/C{base+2},0)', '0.0%',
         'vCPU consumida / provisionada. Mostra o quanto o servidor esta ocioso.'),
        ('Memoria maxima observada (GB)', f'=IFERROR(F{lin_metrica["mem_mb"]}/1024,"")', '0.00',
         'Pico de RAM. Base para o piso do sizing.'),
        ('Memoria provisionada hoje (GB)', f'=IFERROR(AVERAGE({rng("mem_tot_mb")})/1024,"")', '0.00',
         'RAM total do servidor de origem.'),
    ]
    lin_conv = {}
    for nome, f_, fmt, obs in conversoes:
        wm.cell(r, 2, nome).font = BD
        c = wm.cell(r, 3, f_)
        c.font, c.number_format, c.border = NM, fmt, BOX
        c.alignment = Alignment(horizontal='center')
        wm.cell(r, 10, obs).font = SM
        lin_conv[nome] = r
        r += 1

    if pct_ativo < 1:
        r += 1
        c = wm.cell(r, 2, 'ATENCAO: httpd inativo em parte ou em todas as amostras. Estes numeros sao a BASELINE '
                          'do servidor sem Apache no ar. Use-os como PISO no sizing abaixo.')
        c.font, c.fill = WARN, F_AL
        c.alignment = Alignment(wrap_text=True, vertical='center')
        wm.merge_cells(start_row=r, start_column=2, end_row=r, end_column=10)
        wm.row_dimensions[r].height = 30

    # -------- 1-5. SIZING DO SERVIDOR NOVO -------------------------
    r += 2
    wm.cell(r, 2, 'DIMENSIONAMENTO DO SERVIDOR APACHE NOVO').font = Font(name=FONTE, size=12, bold=True, color='1F3864')
    r += 1
    wm.cell(r, 2, 'Preencha/ajuste apenas as celulas AMARELAS. Todo o resto e formula.').font = SM
    r += 1

    r += 1
    r = _bloco(wm, r, '1. BASELINE MEDIDA (vem do resumo acima)')
    r = _linha(wm, r, 'vCPU consumidas — media', f"=C{lin_conv['vCPU medias consumidas']}",
               '0.00', 'Load 1min medio.', 'link')
    r = _linha(wm, r, 'vCPU consumidas — P95', f"=C{lin_conv['vCPU consumidas no P95']}",
               '0.00', 'Pico observado na janela.', 'link'); B_CPU = r - 1
    r = _linha(wm, r, 'RAM do SO + agentes — pico (GB)',
               f"=C{lin_conv['Memoria maxima observada (GB)']}", '0.00',
               'Piso de memoria: consumo do SO. Ponto de partida do sizing.', 'link'); B_RAM = r - 1
    r = _linha(wm, r, 'vCPU provisionadas no servidor atual',
               f"=C{lin_conv['vCPU provisionadas hoje']}", '0',
               'Referencia do ambiente de origem.', 'link')

    r += 1
    r = _bloco(wm, r, '2. PARAMETROS DE PROJECAO (ajuste aqui)')
    r = _linha(wm, r, 'Requisicoes/segundo esperadas no pico', params['rps'], '#,##0',
               'ESTIMATIVA. Os logs nao trazem taxa de requisicoes. Pegue do access_log do ambiente atual.',
               'input'); P_RPS = r - 1
    r = _linha(wm, r, 'CPU por requisicao (ms)', params['ms'], '0.0',
               'Premissa. Estatico: 2-5 ms. Dinamico com proxy: ~15 ms. Aplicacao pesada: 50 ms+.',
               'input'); P_MS = r - 1
    r = _linha(wm, r, 'MaxRequestWorkers (workers simultaneos)', params['workers'], '#,##0',
               'Default do prefork e 256. Ajuste conforme o httpd.conf planejado.', 'input'); P_WRK = r - 1
    r = _linha(wm, r, 'RAM por worker httpd (MB)', params['mb_worker'], '0',
               'Premissa. prefork+PHP: 40-80 MB. worker/event: 5-15 MB.', 'input'); P_MBW = r - 1
    r = _linha(wm, r, 'Fator de crescimento projetado', params['crescimento'], '0.00',
               'Multiplicador para o horizonte de vida do servidor (1,5 = +50%).', 'input'); P_GRW = r - 1
    r = _linha(wm, r, 'Headroom alvo (folga em pico)', params['headroom'], '0%',
               'Percentual que deve permanecer livre no pico. 30% e o usual para web.', 'input'); P_HD = r - 1

    r += 1
    r = _bloco(wm, r, '3. CPU RECOMENDADA')
    r = _linha(wm, r, 'vCPU para atender as requisicoes', f'=C{P_RPS}*C{P_MS}/1000', '0.00',
               'req/s x ms por request / 1000 = nucleos ocupados em regime.'); C_REQ = r - 1
    r = _linha(wm, r, 'vCPU do SO (baseline medida)', f'=C{B_CPU}', '0.00',
               'Overhead do sistema, medido nos logs (P95).'); C_SO = r - 1
    r = _linha(wm, r, 'vCPU com crescimento aplicado', f'=(C{C_REQ}+C{C_SO})*C{P_GRW}', '0.00',
               'Soma da carga x fator de crescimento.'); C_GRW = r - 1
    r = _linha(wm, r, 'vCPU RECOMENDADAS (com headroom)', f'=ROUNDUP(C{C_GRW}/(1-C{P_HD}),0)', '0',
               'Resultado final. Considere arredondar para numero par em VM.'); C_FIM = r - 1
    wm.cell(C_FIM, 2).font = Font(name=FONTE, size=11, bold=True, color='1F3864')
    wm.cell(C_FIM, 3).font = DEST

    r += 1
    r = _bloco(wm, r, '4. MEMORIA RECOMENDADA')
    r = _linha(wm, r, 'RAM do Apache (GB)', f'=C{P_WRK}*C{P_MBW}/1024', '0.00',
               'MaxRequestWorkers x RAM por worker: pior caso do pool cheio.'); M_AP = r - 1
    r = _linha(wm, r, 'RAM do SO + agentes (GB)', f'=C{B_RAM}', '0.00',
               'Piso medido nos logs.'); M_SO = r - 1
    r = _linha(wm, r, 'RAM com crescimento aplicado', f'=(C{M_AP}+C{M_SO})*C{P_GRW}', '0.00',
               'Soma x fator de crescimento.'); M_GRW = r - 1
    r = _linha(wm, r, 'RAM RECOMENDADA (GB, com headroom)', f'=ROUNDUP(C{M_GRW}/(1-C{P_HD}),0)', '0',
               'Suba para o proximo valor comercial (8 / 16 / 32 GB).'); M_FIM = r - 1
    wm.cell(M_FIM, 2).font = Font(name=FONTE, size=11, bold=True, color='1F3864')
    wm.cell(M_FIM, 3).font = DEST

    r += 1
    r = _bloco(wm, r, '5. DISCO RECOMENDADO')
    lin_disco = {}
    for mnt in mounts:
        usados = [x['_discos'][mnt]['usado_gb'] for x in regs
                  if mnt in x['_discos'] and x['_discos'][mnt]['usado_gb'] is not None]
        totais = [x['_discos'][mnt]['total_gb'] for x in regs
                  if mnt in x['_discos'] and x['_discos'][mnt]['total_gb'] is not None]
        if not usados:
            continue
        r = _linha(wm, r, f'{mnt} usado hoje (GB)', round(max(usados), 1), '0.0',
                   f'Maximo observado nos logs. Provisionado hoje: {max(totais):.0f} GB.'
                   if totais else 'Maximo observado nos logs.', 'input')
        lin_disco[mnt] = r - 1

    for mnt, lin in lin_disco.items():
        extra = ('Mantenha /var e /var/log em particoes separadas para a raiz nunca encher com access_log.'
                 if mnt == '/' else 'Revise se o servidor novo tambem hospedar o batch.')
        r = _linha(wm, r, f'{mnt} RECOMENDADO (GB)',
                   f'=ROUNDUP(C{lin}*C{P_GRW}/(1-C{P_HD})/10,0)*10', '0',
                   'Arredondado para o proximo multiplo de 10 GB. ' + extra)
        wm.cell(r - 1, 2).font = Font(name=FONTE, size=11, bold=True, color='1F3864')
        wm.cell(r - 1, 3).font = DEST
        lin_disco[mnt] = r - 1   # passa a apontar para a linha do RECOMENDADO

    r += 2
    c = wm.cell(r, 2, 'RESUMO DA RECOMENDACAO')
    c.font, c.fill = H2, F_H2
    wm.merge_cells(start_row=r, start_column=2, end_row=r, end_column=5)
    r += 1
    finais = [('vCPU', f'=C{C_FIM}'), ('RAM (GB)', f'=C{M_FIM}')]
    finais += [(f'Disco {m} (GB)', f'=C{l}') for m, l in lin_disco.items()]
    for rotulo, ref in finais:
        wm.cell(r, 2, rotulo).font = Font(name=FONTE, size=11, bold=True)
        c = wm.cell(r, 3, ref)
        c.font, c.number_format, c.border = FINAL, '0', BOX
        c.alignment = Alignment(horizontal='center')
        r += 1

    r += 1
    c = wm.cell(r, 2, 'Premissas em amarelo sao estimativas, nao medicoes. Valide req/s e ms por requisicao '
                      'contra o access_log do ambiente atual antes de fechar o provisionamento.')
    c.font, c.fill = WARN, F_AL
    c.alignment = Alignment(wrap_text=True, vertical='top')
    wm.merge_cells(start_row=r, start_column=2, end_row=r + 1, end_column=5)
    wm.row_dimensions[r].height = 28

    wm.cell(P_RPS, 3).comment = Comment(
        'Origem: parametro informado na execucao do script, nao medido. '
        'Substitua pelo valor real do access_log.', 'capacity_apache.py', height=110, width=280)
    wm.cell(P_MS, 3).comment = Comment(
        'Premissa de referencia, nao medida neste ambiente.', 'capacity_apache.py',
        height=110, width=280)

    wb.save(destino)


# =====================================================================
# 4. CLI
# =====================================================================

def main():
    ap = argparse.ArgumentParser(
        description='Gera planilha de capacity a partir dos logs de health check Apache. '
                    'Sem argumentos, usa o bloco CONFIGURACAO no topo do arquivo.',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='Exemplos:\n'
               '  python capacity_apache.py\n'
               '  python capacity_apache.py D:\\logs\\apache -o capacity.xlsx --rps 250')
    ap.add_argument('entrada', nargs='*',
                    help='pasta, arquivo(s) ou padrao glob dos logs. Omitido: usa PASTA_LOGS')
    ap.add_argument('-o', '--out',   default=ARQUIVO_SAIDA, help='arquivo .xlsx de saida')
    ap.add_argument('--host',        default=HOST, help='processa apenas este host')
    ap.add_argument('--recursivo',   dest='recursivo', action='store_true',  default=BUSCAR_SUBPASTAS)
    ap.add_argument('--sem-subpastas', dest='recursivo', action='store_false',
                    help='ignora subpastas de PASTA_LOGS')
    ap.add_argument('--rps',         type=float, default=RPS_ESPERADO,  help='requisicoes/s no pico')
    ap.add_argument('--ms-por-req',  type=float, default=MS_POR_REQ, dest='ms', help='CPU em ms por requisicao')
    ap.add_argument('--workers',     type=int,   default=MAX_WORKERS,   help='MaxRequestWorkers')
    ap.add_argument('--mb-worker',   type=float, default=MB_POR_WORKER, help='RAM por worker httpd em MB')
    ap.add_argument('--crescimento', type=float, default=FATOR_CRESC,   help='fator de crescimento')
    ap.add_argument('--headroom',    type=float, default=HEADROOM,      help='folga alvo, 0 a 1')
    args = ap.parse_args()

    if not 0 <= args.headroom < 1:
        sys.exit('Erro: headroom deve estar entre 0 e 0.99')

    entrada = args.entrada or [PASTA_LOGS]

    # valida a pasta antes de varrer, para dar um erro legivel
    for e in entrada:
        if not os.path.exists(e) and not glob.glob(e):
            sys.exit(f'Erro: caminho nao encontrado -> {e}\n'
                     f'       (resolvido como: {os.path.abspath(e)})\n'
                     '       Ajuste PASTA_LOGS no topo do script ou informe a pasta na linha de comando.')

    print(f'lendo logs de: {os.path.abspath(entrada[0]) if len(entrada) == 1 else ", ".join(entrada)}'
          f'{"  (incluindo subpastas)" if args.recursivo else ""}')

    regs, ignorados = coletar(entrada, args.host, args.recursivo)
    if not regs:
        alvo = ', '.join(entrada)
        extra = f' para o host {args.host}' if args.host else ''
        sys.exit(f'Erro: nenhum log valido encontrado em {alvo}{extra}.\n'
                 '       Verifique se os arquivos .log estao na pasta e se contem o cabecalho '
                 '"HEALTH CHECK APACHE".')

    destino = os.path.abspath(args.out)
    os.makedirs(os.path.dirname(destino) or '.', exist_ok=True)
    gerar_planilha(regs, ignorados, {
        'rps': args.rps, 'ms': args.ms, 'workers': args.workers,
        'mb_worker': args.mb_worker, 'crescimento': args.crescimento,
        'headroom': args.headroom}, destino)

    hosts = sorted({r['host'] for r in regs})
    ativos = sum(r['httpd_ativo'] for r in regs)
    print(f'{len(regs)} logs processados  |  host(s): {", ".join(hosts)}')
    print(f'janela: {regs[0]["data"]} {regs[0]["hora"]}  ->  {regs[-1]["data"]} {regs[-1]["hora"]}')
    print(f'httpd ativo em {ativos}/{len(regs)} amostras ({ativos / len(regs) * 100:.0f}%)')
    if ativos < len(regs):
        print('AVISO: baseline coletada com o Apache fora do ar em parte das amostras — '
              'trate os numeros como piso, nao como carga de producao.')
    for nome, motivo in ignorados:
        print(f'ignorado: {nome} ({motivo})')
    print(f'planilha gerada: {destino}')
    print('Abra no Excel/LibreOffice uma vez para que as formulas sejam calculadas.')


if __name__ == '__main__':
    main()

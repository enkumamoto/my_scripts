#!/usr/bin/env python3
import argparse
import shutil
import sys
from pathlib import Path

ORIGEM_PADRAO = "/Volumes/EXTERNO"
BACKUP_PADRAO = "/Users/ronin/Documents/bkp"

PASTAS_IGNORADAS = {
    "System Volume Information",
    "$RECYCLE.BIN",
    ".Spotlight-V100",
    ".Trashes",
    ".fseventsd",
    ".TemporaryItems",
    "found.000",
}

ARQUIVOS_IGNORADOS = {
    ".DS_Store",
    "Thumbs.db",
    "desktop.ini",
    ".localized",
}


def parse_args():
    p = argparse.ArgumentParser(
        description="Compara arquivos entre origem e backup e copia os faltantes."
    )
    p.add_argument("origem", nargs="?", default=ORIGEM_PADRAO,
                   help=f"Pasta de origem (padrao: {ORIGEM_PADRAO})")
    p.add_argument("backup", nargs="?", default=BACKUP_PADRAO,
                   help=f"Pasta de backup (padrao: {BACKUP_PADRAO})")
    p.add_argument("--modo", choices=["comparar", "copiar", "ambos"], default=None,
                   help="comparar: so mostra o relatorio; copiar: so copia os faltantes; "
                        "ambos: compara e copia. Se omitido, pergunta interativamente.")
    p.add_argument("--dry-run", action="store_true",
                   help="Apenas mostra o que seria copiado, sem copiar de fato.")
    p.add_argument("--check-size", action="store_true",
                   help="Considera desatualizado (e recopia) se o tamanho diferir.")
    p.add_argument("--incluir-tudo", action="store_true",
                   help="Nao ignora arquivos/pastas de sistema (copia literalmente tudo).")
    p.add_argument("--inverter", action="store_true",
                   help="Inverte o sentido: usa backup como origem e origem como destino "
                        "(copia do backup para a origem).")
    return p.parse_args()


def deve_ignorar(caminho_relativo: Path, incluir_tudo: bool) -> bool:
    if incluir_tudo:
        return False
    for parte in caminho_relativo.parts[:-1]:
        if parte in PASTAS_IGNORADAS:
            return True
    if caminho_relativo.name in ARQUIVOS_IGNORADOS:
        return True
    return False


def escolher_modo_interativo() -> str:
    opcoes = {"1": "comparar", "2": "copiar", "3": "ambos"}
    print("Nenhum modo informado. O que voce quer fazer?")
    print("  1) Somente comparar (mostra o relatorio, nao copia nada)")
    print("  2) Somente copiar (copia os arquivos faltantes, sem relatorio)")
    print("  3) Comparar e copiar (relatorio completo + copia)")
    while True:
        escolha = input("Escolha [1/2/3]: ").strip()
        if escolha in opcoes:
            return opcoes[escolha]
        print("Opcao invalida, tente novamente.")


def escolher_direcao_interativa() -> bool:
    opcoes = {"1": False, "2": True}
    print("Qual o sentido da copia?")
    print("  1) Origem -> Backup (padrao)")
    print("  2) Backup -> Origem (inverter)")
    while True:
        escolha = input("Escolha [1/2]: ").strip()
        if escolha in opcoes:
            return opcoes[escolha]
        print("Opcao invalida, tente novamente.")


def main():
    args = parse_args()

    modo_interativo = args.modo is None
    modo = args.modo or escolher_modo_interativo()
    if modo_interativo and not args.inverter:
        args.inverter = escolher_direcao_interativa()
    mostrar_comparacao = modo in ("comparar", "ambos")
    copiar_arquivos = modo in ("copiar", "ambos")

    if args.inverter:
        origem = Path(args.backup)
        backup = Path(args.origem)
    else:
        origem = Path(args.origem)
        backup = Path(args.backup)

    copiar_arquivos = copiar_arquivos and not args.dry_run

    if not origem.is_dir():
        print(f"ERRO: pasta de origem nao encontrada: {origem}")
        sys.exit(1)
    if not backup.exists():
        print(f"AVISO: pasta de backup nao existe. Sera criada: {backup}")
        if copiar_arquivos:
            backup.mkdir(parents=True, exist_ok=True)

    print(f"Origem : {origem}")
    print(f"Backup : {backup}")
    print(f"Modo   : {modo}" + (" (dry-run, nenhum arquivo sera copiado)" if args.dry_run else ""))
    if args.incluir_tudo:
        print("Filtro : DESLIGADO (copiando inclusive arquivos de sistema)")
    else:
        print("Filtro : ligado (ignorando arquivos/pastas de sistema)")
    print("-" * 60)

    total = 0
    ignorados = 0
    faltando = 0
    tamanho_diferente = 0
    copiados = 0
    erros = 0

    for arquivo in origem.rglob("*"):
        if not arquivo.is_file():
            continue

        relativo = arquivo.relative_to(origem)

        if deve_ignorar(relativo, args.incluir_tudo):
            ignorados += 1
            continue

        total += 1
        destino = backup / relativo

        precisa_copiar = False
        motivo = ""

        if not destino.exists():
            precisa_copiar = True
            motivo = "nao existe no backup"
            faltando += 1
        elif args.check_size and arquivo.stat().st_size != destino.stat().st_size:
            precisa_copiar = True
            motivo = "tamanho diferente"
            tamanho_diferente += 1

        if precisa_copiar:
            if mostrar_comparacao and motivo == "nao existe no backup":
                print(f"[ALERTA] {relativo}")
                print(f"         local: {arquivo}")
            if not copiar_arquivos:
                continue
            try:
                destino.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(arquivo, destino)
                copiados += 1
                if mostrar_comparacao:
                    print(f"         copiado para: {destino}")
            except Exception as e:
                erros += 1
                print(f"         ERRO ao copiar: {e}")

    print("-" * 60)
    print("RESUMO")
    print(f"  Arquivos verificados na origem : {total}")
    print(f"  Ignorados (sistema)            : {ignorados}")
    print(f"  Faltando no backup             : {faltando}")
    if args.check_size:
        print(f"  Com tamanho diferente          : {tamanho_diferente}")
    if not copiar_arquivos:
        print("  (nenhum arquivo foi copiado)")
    else:
        print(f"  Copiados com sucesso           : {copiados}")
        print(f"  Erros de copia                 : {erros}")


if __name__ == "__main__":
    main()

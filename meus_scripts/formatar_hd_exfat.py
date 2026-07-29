#!/usr/bin/env python3
import plistlib
import subprocess
import sys


def diskutil(*args, capture=True):
    cmd = ["diskutil", *args]
    return subprocess.run(cmd, capture_output=capture, text=True)


def diskutil_plist(*args):
    verbo, resto = args[0], args[1:]
    res = subprocess.run(["diskutil", verbo, "-plist", *resto],
                         capture_output=True, text=True)
    if res.returncode != 0:
        raise RuntimeError(res.stderr.strip() or "falha no diskutil")
    return plistlib.loads(res.stdout.encode())


def formata_tamanho(num_bytes):
    if not num_bytes:
        return "tamanho desconhecido"
    tb = 1024 ** 4
    gb = 1024 ** 3
    if num_bytes >= tb:
        return f"{num_bytes / tb:.2f} TB"
    return f"{num_bytes / gb:.2f} GB"


def info_disco(dev):
    try:
        info = diskutil_plist("info", dev)
    except RuntimeError:
        return ("?", 0, False)
    nome = info.get("MediaName") or info.get("IORegistryEntryName") or "?"
    tamanho = info.get("TotalSize") or info.get("Size") or 0
    is_internal = bool(info.get("Internal", False))
    return (nome, tamanho, is_internal)


def lista_discos_externos():
    try:
        dados = diskutil_plist("list", "external", "physical")
    except RuntimeError as e:
        print(f"ERRO ao listar discos: {e}")
        sys.exit(1)
    ids = dados.get("WholeDisks", [])
    return [f"/dev/{d}" for d in ids]


def confirmar_formatacao(dev, nome):
    print()
    print("=" * 63)
    print(f" DISCO A SER FORMATADO: {dev}")
    print("=" * 63)
    res = diskutil("list", dev)
    if res.stdout:
        print(res.stdout.rstrip())
    print("-" * 63)
    nome_disco, tamanho, _ = info_disco(dev)
    print(f" Nome do dispositivo : {nome_disco}")
    print(f" Tamanho             : {formata_tamanho(tamanho)}")
    print("=" * 63)
    print()
    print(f">>> TODOS OS DADOS em {dev} serao APAGADOS PERMANENTEMENTE. <<<")
    print(f'>>> Novo formato: exFAT   |   Nome do volume: "{nome}"')
    print()

    c1 = input("Confirma a formatacao deste disco? Digite APAGAR para continuar: ").strip()
    if c1 != "APAGAR":
        print("Cancelado. Nada foi alterado.")
        return False

    c2 = input(f"Ultima confirmacao: formatar {dev} em exFAT agora? (s/N): ").strip()
    if c2.lower() != "s":
        print("Cancelado. Nada foi alterado.")
        return False

    return True


def main():
    nome_volume = sys.argv[1] if len(sys.argv) > 1 else "EXTERNO"

    if sys.platform != "darwin":
        print("ERRO: este script foi feito para macOS (usa 'diskutil').")
        print("Em Linux use mkfs.exfat; no Windows use o Gerenciador de Disco / format.")
        sys.exit(1)

    print("Procurando discos externos conectados...")
    discos = lista_discos_externos()

    if not discos:
        print()
        print("Nenhum disco externo encontrado.")
        print("Conecte o HD/pendrive externo e rode o script novamente.")
        sys.exit(1)

    if len(discos) == 1:
        dev = discos[0]
        nome_disco, tamanho, _ = info_disco(dev)
        print("\nDisco externo encontrado:")
        print(f"  {dev}  ->  {nome_disco}  ({formata_tamanho(tamanho)})")
    else:
        print("\nForam encontrados varios discos externos. Escolha qual formatar:\n")
        for i, d in enumerate(discos, start=1):
            nome_disco, tamanho, _ = info_disco(d)
            print(f"  [{i}] {d}  ->  {nome_disco}  ({formata_tamanho(tamanho)})")
        print()
        escolha = input("Digite o numero do disco (ou 'q' para sair): ").strip()
        if escolha.lower() == "q":
            print("Cancelado.")
            sys.exit(0)
        if not escolha.isdigit() or not (1 <= int(escolha) <= len(discos)):
            print("Escolha invalida. Cancelado.")
            sys.exit(1)
        dev = discos[int(escolha) - 1]

    _, tamanho, is_internal = info_disco(dev)
    if is_internal:
        print("\n!!!  PARADO POR SEGURANCA  !!!")
        print("O disco selecionado aparece como INTERNO. O script nao formata")
        print("discos internos para evitar apagar o sistema.")
        sys.exit(1)

    if not confirmar_formatacao(dev, nome_volume):
        sys.exit(0)

    esquema = "MBRFormat"
    if tamanho and tamanho > 2 * (1024 ** 4):
        esquema = "GPT"
        print("Disco maior que 2TB detectado -> usando esquema GPT.")

    print("\nDesmontando e formatando... (pode levar alguns segundos)")
    diskutil("unmountDisk", dev, capture=False)

    res = subprocess.run(
        ["diskutil", "eraseDisk", "exFAT", nome_volume, esquema, dev],
        text=True,
    )
    if res.returncode != 0:
        print("\nERRO: a formatacao falhou. Verifique se o disco nao esta em uso.")
        sys.exit(1)

    print("\n" + "=" * 63)
    print(f' CONCLUIDO! Disco formatado em exFAT como "{nome_volume}".')
    print(" Agora Windows, macOS e Linux podem ler e escrever nele.")
    print("=" * 63)
    final = diskutil("list", dev)
    if final.stdout:
        print(final.stdout.rstrip())


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nCancelado pelo usuario.")
        sys.exit(1)

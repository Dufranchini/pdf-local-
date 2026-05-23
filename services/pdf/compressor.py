import os
from pathlib import Path
from typing import NamedTuple

import fitz  # PyMuPDF — já instalado via pdf2docx

from logger import get_logger

log = get_logger("compressor")


# ══════════════════════════════════════════════════════
#  LIMITES E CONFIGURAÇÃO
# ══════════════════════════════════════════════════════

MIN_REDUCTION_PERCENT = 5.0

MAX_PDF_OBJECTS = 50_000


# ══════════════════════════════════════════════════════
#  ESTRUTURA DE RETORNO
# ══════════════════════════════════════════════════════
class CompressionResult(NamedTuple):
    """Resultado da operação de compressão."""
    output_path: str          
    original_size: int        
    compressed_size: int      
    reduction_percent: float  
    pages: int
    was_compressed: bool      
    metadata_cleared: bool    


# ══════════════════════════════════════════════════════
#  Helpers (testáveis isoladamente)
# ══════════════════════════════════════════════════════

def _calcular_reducao(original: int, comprimido: int) -> float:
    """
    Calcula percentual de redução. Defensivo contra divisão por zero
    e tamanhos negativos (não deveria acontecer, mas...).
    """
    if original <= 0:
        return 0.0
    if comprimido < 0:
        return 0.0
    reducao = ((original - comprimido) / original) * 100
    # Pode ser negativa se a compressão AUMENTOU o tamanho
    # (acontece em PDFs já muito otimizados)
    return round(reducao, 2)


def _detectar_pdf_bomb(doc) -> bool:
    try:
        # xref_length é o número de objetos no PDF — barato de obter
        n_objects = doc.xref_length()
        if n_objects > MAX_PDF_OBJECTS:
            log.warning(
                f"PDF rejeitado por suspeita de bomba: "
                f"{n_objects} objetos (limite: {MAX_PDF_OBJECTS})"
            )
            return True
    except Exception as e:
        # Se nem conseguimos ler n_objects, algo está errado.
        # Por precaução, tratamos como suspeito.
        log.warning(f"Não foi possível avaliar n_objects (suspeito): {e}")
        return True
    return False


# ══════════════════════════════════════════════════════
#  Compressão principal
# ══════════════════════════════════════════════════════

def compress_pdf(input_path: str, output_path: str) -> CompressionResult:

    log.info(f"Iniciando compressão: {input_path}")

    input_path  = Path(input_path)
    output_path = Path(output_path)

    if not input_path.exists():
        # Erro real, não input inválido — propaga como exceção genérica
        raise FileNotFoundError(f"Arquivo de entrada não existe: {input_path}")

    original_size = input_path.stat().st_size
    if original_size == 0:
        raise ValueError("O arquivo enviado está vazio.")

    doc = None
    try:
        # ── Abre o PDF ──
        try:
            doc = fitz.open(str(input_path))
        except Exception as e:
            # Não conseguimos nem abrir = PDF corrompido / não é PDF
            log.warning(f"PDF não pôde ser aberto: {e}")
            raise ValueError("Arquivo PDF inválido ou corrompido.")

        # ── Validação: PDF criptografado ──
        if doc.is_encrypted:
            # Tenta abrir sem senha (vazia). Se ainda for True, é protegido.
            if not doc.authenticate(""):
                log.warning(f"PDF criptografado rejeitado: {input_path.name}")
                raise ValueError("O PDF está protegido por senha. Remova a proteção antes de comprimir.")

        # ── Validação: PDF-bomb ──
        if _detectar_pdf_bomb(doc):
            raise ValueError(
                "Este PDF possui estrutura interna anormal e foi recusado por segurança. "
                "Se este for um arquivo legítimo, entre em contato com o suporte."
            )

        n_pages = doc.page_count
        if n_pages == 0:
            raise ValueError("O PDF não contém páginas válidas.")

        log.info(f"PDF aceito: {n_pages} página(s), {original_size} bytes")

        try:
            doc.set_metadata({})
            metadata_cleared = True
            log.debug("Metadados limpos")
        except Exception as e:
            # Falha cosmética — segue mesmo assim, só não zerou metadados
            log.warning(f"Falha ao limpar metadados (não fatal): {e}")
            metadata_cleared = False

        # ── Salva comprimido ──
        try:
            doc.save(
                str(output_path),
                garbage=4,              # remove objetos órfãos (nível máximo)
                deflate=True,           # comprime streams via zlib
                deflate_images=True,    # comprime imagens (sem perda)
                clean=True,             # limpa estruturas inválidas
            )
        except Exception as e:
            log.error(f"Falha ao salvar comprimido: {e}", exc_info=True)
            raise Exception(f"Falha ao gerar PDF comprimido: {e}")

    finally:
        if doc is not None:
            try:
                doc.close()
            except Exception:
                pass  # não propaga erro de cleanup

    # ── Avalia o resultado ──
    if not output_path.exists():
        raise Exception("PDF comprimido não foi gerado (output inexistente).")

    compressed_size = output_path.stat().st_size
    reducao = _calcular_reducao(original_size, compressed_size)

    log.info(
        f"Compressão concluída: {original_size} → {compressed_size} bytes "
        f"({reducao:.1f}%)"
    )

    if reducao < MIN_REDUCTION_PERCENT:
        log.info(
            f"Redução insuficiente ({reducao:.1f}% < {MIN_REDUCTION_PERCENT}%) "
            f"— devolvendo arquivo original"
        )
        # Remove o comprimido inútil e copia o original pro output
        try:
            output_path.unlink()
        except Exception as e:
            log.warning(f"Falha removendo comprimido inútil: {e}")

        # Copia bytes do original pro output (mais seguro que rename
        # cross-device em sistemas com /tmp em mount diferente)
        try:
            output_path.write_bytes(input_path.read_bytes())
        except Exception as e:
            log.error(f"Falha copiando original como output: {e}", exc_info=True)
            raise Exception(f"Falha ao devolver arquivo original: {e}")

        return CompressionResult(
            output_path=str(output_path),
            original_size=original_size,
            compressed_size=original_size,  # =original, pois devolvemos o original
            reduction_percent=0.0,
            pages=n_pages,
            was_compressed=False,
            metadata_cleared=False,  # não limpamos pois devolvemos original
        )

    return CompressionResult(
        output_path=str(output_path),
        original_size=original_size,
        compressed_size=compressed_size,
        reduction_percent=reducao,
        pages=n_pages,
        was_compressed=True,
        metadata_cleared=metadata_cleared,
    )
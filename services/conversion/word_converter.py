import io
import re
from pathlib import Path

import fitz                         # PyMuPDF — extração/renderização de PDF
from docx import Document           # python-docx — montagem do DOCX final
from pdf2docx import Converter      # Abordagem 1 — conversão com layout/texto

from logger import get_logger

log = get_logger("word_converter")


# ══════════════════════════════════════════════════════
#  Constantes — Abordagem 1 (pdf2docx com layout/texto)
# ══════════════════════════════════════════════════════
MAX_PAGES = 50   # cobre a esmagadora maioria dos casos corporativos


# ══════════════════════════════════════════════════════
#  Constantes — Abordagem 2 (página → imagem de alta res)
# ══════════════════════════════════════════════════════
# [S4] Faixa de DPI permitida — acima de 200 DPI o custo de RAM é proibitivo
#      (A4 a 300 DPI ≈ 26 MB/pág descomprimido; a 200 DPI ≈ 11 MB/pág)
_DPI_MIN = 72
_DPI_MAX = 200

# [S5] Pixels máximos por eixo (largura OU altura) de um único pixmap.
#      3000 px × 3000 px = 9 MP ≈ 27 MB por página — seguro para o servidor.
#      Previne OOM causado por PDFs com media box absurdamente grande.
_MAX_AXIS_PX = 3_000

# [S6] Tamanho máximo acumulado do DOCX de saída (80 MB).
#      Previne esgotamento de disco em conversões pesadas.
_MAX_OUTPUT_BYTES = 80 * 1024 * 1024   # 80 MB

# [S3] Whitelist de caracteres seguros para o nome do arquivo de saída.
#      Qualquer coisa fora disso é substituída por '_'.
_SAFE_STEM_RE = re.compile(r"[^\w\-]")
_MAX_STEM_LEN = 64

# [S11] Tamanho máximo do arquivo de entrada aceito pelo service layer.
#       O router já limita uploads a 10 MB — este limite (15 MB) é defesa em
#       profundidade: protege chamadas diretas ao service (CLI, testes, outros
#       routers) E garante que o PdfReader não comece a parsear antes da
#       verificação de tamanho atuar.
#
#       Por que isso importa:
#         pypdf.PdfReader() executa parsing completo ao ser instanciado.
#         Um PDF de 9 MB com xref streams aninhados pode expandir para
#         centenas de MB em RAM ANTES de qualquer validação de páginas.
#         O check de stat().st_size é O(1) e custa zero.
_MAX_INPUT_BYTES = 15 * 1024 * 1024   # 15 MB


# ══════════════════════════════════════════════════════
#  Guardas de segurança — Abordagem 2
#  (service layer não confia no caller)
# ══════════════════════════════════════════════════════

def _verificar_symlink(path: Path) -> None:
    """
    [S1] Rejeita symlinks no arquivo de entrada e no diretório de saída.

    Ataque que previne:
      Um atacante cria 'upload.pdf' → symlink para '/etc/shadow'.
      Sem esta checagem, fitz.open() abriria o arquivo real sem reclamar.
    """
    if path.is_symlink():
        raise ValueError(
            f"Arquivo inválido: symlinks não são aceitos por razões de segurança."
        )


def _validar_magic_bytes(path: Path) -> None:
    """
    [S2] Valida a assinatura binária real do arquivo — não confia na extensão.

    Ataque que previne:
      Usuário renomeia 'virus.exe' para 'relatorio.pdf'.
      A extensão passa na whitelist do router, mas o magic byte falha aqui.

    Nota: o router já faz esta checagem durante o upload (leitura em chunks).
    Repetimos aqui porque este service pode ser chamado de qualquer lugar
    (CLI, testes, outro router) — defesa em profundidade.
    """
    try:
        with open(path, "rb") as f:
            header = f.read(5)
    except OSError as exc:
        raise ValueError(f"Não foi possível ler o arquivo: {exc}") from exc

    if header != b"%PDF-":
        raise ValueError(
            "O arquivo enviado não é um PDF válido (assinatura binária inválida)."
        )


def _sanitizar_stem(stem: str) -> str:
    """
    [S3] Remove caracteres perigosos do stem antes de construir o path de saída.

    Ataque que previne:
      input_path.stem = '../../etc/cron.d/malicious'
      Sem sanitização: output_dir / '../../etc/cron.d/malicious.docx'
                       → escreve fora do diretório permitido.

    Também previne:
      - Dot-files (ex: '.bashrc') via lstrip('.')
      - Nomes excessivamente longos que estourem o limite do FS
    """
    sanitized = _SAFE_STEM_RE.sub("_", stem)
    sanitized = sanitized.lstrip(".")       # sem arquivos ocultos
    sanitized = sanitized[:_MAX_STEM_LEN]  # sem nomes quilométricos
    return sanitized if sanitized else "converted"


def _dpi_seguro(dpi: int) -> int:
    """
    [S4] Força o DPI para a faixa [_DPI_MIN, _DPI_MAX] independente do input.

    Ataque que previne:
      Caller passa dpi=10_000 (intencionalmente ou por bug).
      A4 a 10k DPI → ~69.444 × 98.222 px → ~20 GB de RAM → servidor derruba.
    """
    return max(_DPI_MIN, min(_DPI_MAX, int(dpi)))


def _matrix_segura(page: "fitz.Page", dpi: int) -> "fitz.Matrix":
    """
    [S5] Calcula a matriz de transformação garantindo que nenhum eixo
    do pixmap resultante exceda _MAX_AXIS_PX pixels.

    Ataque que previne:
      PDF com media box de 100.000 × 100.000 pontos (válido pela spec).
      A 200 DPI: ~277.778 × 277.778 px → 76 GB de RAM por página → OOM.

    Comportamento: se a página seria maior que o limite, o scale é reduzido
    proporcionalmente — a imagem fica menor, mas o aspect ratio é preservado.
    """
    scale = dpi / 72.0
    rect = page.rect

    # Calcula o maior eixo para decidir se precisa de capping
    maior_eixo = max(rect.width * scale, rect.height * scale)
    if maior_eixo > _MAX_AXIS_PX:
        scale *= _MAX_AXIS_PX / maior_eixo
        log.warning(
            f"[S5] Página com dimensão elevada detectada "
            f"({rect.width:.0f}×{rect.height:.0f} pt) — "
            f"scale reduzido para {scale:.4f} (anti-OOM)"
        )

    return fitz.Matrix(scale, scale)


# ══════════════════════════════════════════════════════
#  Validação interna do PDF (compartilhada entre as
#  duas abordagens de conversão)
# ══════════════════════════════════════════════════════

def _validar_pdf(input_path: Path) -> int:
    """
    Valida integridade, criptografia e contagem de páginas do PDF.
    Lança ValueError com mensagem amigável para qualquer anomalia.
    Retorna o número de páginas do PDF válido.
    """
    try:
        from pypdf import PdfReader   # já está no requirements via merge.py

        # ── [S11] Tamanho do arquivo ANTES de instanciar o PdfReader ──────
        # O PdfReader executa parsing completo ao ser instanciado — um PDF
        # de 9 MB com objetos aninhados pode expandir para centenas de MB
        # em RAM antes de qualquer outra validação atuar.
        # stat().st_size é O(1): zero custo, impacto máximo.
        try:
            file_size = input_path.stat().st_size
        except OSError as exc:
            raise ValueError(f"Não foi possível verificar o arquivo: {exc}") from exc

        if file_size == 0:
            raise ValueError("O arquivo PDF está vazio.")

        if file_size > _MAX_INPUT_BYTES:
            raise ValueError(
                f"Arquivo muito grande ({file_size // (1024 * 1024)} MB). "
                f"Limite do serviço: {_MAX_INPUT_BYTES // (1024 * 1024)} MB."
            )
        # ──────────────────────────────────────────────────────────────────

        reader = PdfReader(str(input_path))

        if reader.is_encrypted:
            raise ValueError(
                "O PDF está protegido por senha. Remova a proteção antes de converter."
            )

        num_pages = len(reader.pages)

        if num_pages == 0:
            raise ValueError("O PDF não contém páginas válidas.")

        if num_pages > MAX_PAGES:
            raise ValueError(
                f"PDF excede o limite de {MAX_PAGES} páginas "
                f"(encontradas: {num_pages})."
            )

        return num_pages

    except ValueError:
        raise          # mantém a mensagem original
    except Exception as exc:
        raise ValueError(
            f"Arquivo PDF inválido ou corrompido: {exc}"
        ) from exc


# ══════════════════════════════════════════════════════
#  Abordagem 1 — pdf2docx (texto editável + layout)
# ══════════════════════════════════════════════════════

def convert_pdf_to_doc(input_path: str, output_dir: str) -> str:
    """
    Converte PDF → DOCX preservando texto editável e layout.
    Limitação: imagens complexas ou layouts gráficos pesados podem
    ser degradados — use convert_pdf_to_docx_as_images() nesses casos.
    """
    input_path = Path(input_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    output_path = output_dir / f"{input_path.stem}.docx"

    log.info(f"Iniciando conversão PDF → DOCX (Abordagem 1 — pdf2docx): {input_path}")

    num_pages = _validar_pdf(input_path)
    log.info(f"PDF validado: {num_pages} página(s)")

    cv = None
    try:
        cv = Converter(str(input_path))

        # ── Parâmetros otimizados de conversão ────────────────────────
        cv.convert(
            str(output_path),
            start=0,
            end=None,
            multi_processing=False,
            connected_border_tolerance=0.5,   # detecção de bordas conectadas
            max_border_width=6.0,             # largura máx. de borda
            float_image_ignorable_gap=5.0,    # gaps pequenos não quebram parágrafo
            line_overlap_threshold=0.9,       # agrupamento de linhas
            line_break_width_ratio=0.5,       # quebra de linha consistente
            line_break_free_space_ratio=0.1,  # espaços não disparam quebra
            # Detecção de tabelas sem bordas visíveis
            extract_stream_table=True,
            min_border_clearance=2.0,
            max_border_clearance=8.0,
        )

        if not output_path.exists():
            raise FileNotFoundError(
                "A biblioteca pdf2docx executou mas não gerou o arquivo .docx. "
                "Verifique se o PDF não está corrompido."
            )

        log.info(f"Conversão (Abordagem 1) concluída: {output_path}")
        return str(output_path)

    except Exception as exc:
        log.error(f"Erro ao converter {input_path}: {exc}", exc_info=True)
        raise

    finally:
        # Libera handle do PyMuPDF SEMPRE — evita vazamento de file descriptors
        if cv is not None:
            try:
                cv.close()
            except Exception:
                pass


# ══════════════════════════════════════════════════════
#  Abordagem 2 — Página → imagem (fidelidade visual 100%)
# ══════════════════════════════════════════════════════

def convert_pdf_to_docx_as_images(
    input_path: str,
    output_dir: str,
    dpi: int = 150,
) -> str:
    """
    Converte cada página do PDF em imagem de alta resolução e embute no DOCX.
    Preserva 100% do visual original: imagens, gráficos, layouts complexos.

    ⚠️  Desvantagem: o texto NÃO é editável no documento final.
        Use quando a Abordagem 1 (pdf2docx) não preservar imagens/layout.

    Proteções de segurança implementadas
    ────────────────────────────────────
    [S1]  Symlink check — rejeita links simbólicos no input e output_dir
    [S2]  Magic bytes — valida assinatura %PDF- independente da extensão
    [S3]  Sanitização do stem — previne path traversal no nome de saída
    [S4]  DPI clamped — força faixa [72–200], ignora valores do caller
    [S5]  Matrix segura — cap de _MAX_AXIS_PX px por eixo (anti-OOM)
    [S6]  Limite de output — aborta se o DOCX exceder _MAX_OUTPUT_BYTES
    [S7]  Liberação de memória — del explícito do pixmap após cada página
    [S8]  Limpeza de arquivo parcial — unlink em caso de erro
    [S9]  Verificação do arquivo final — confirma existência e tamanho
    [S10] JavaScript do PDF — PyMuPDF NÃO executa JS em get_pixmap()
          (renderização de pixels não aciona o motor JS do PDF)
    [S11] Tamanho de entrada — stat().st_size verificado ANTES do PdfReader
          (evita decompression bomb antes das validações atuarem)
    [S12] Double-check de páginas — len(pdf_doc) validado após fitz.open()
          (pypdf e PyMuPDF podem discordar em PDFs malformados)
    """
    input_path = Path(input_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # ── [S1] Symlink check ────────────────────────────────────────────
    _verificar_symlink(input_path)
    _verificar_symlink(output_dir)

    # ── [S2] Magic bytes ──────────────────────────────────────────────
    _validar_magic_bytes(input_path)

    # ── [S3] Sanitização do nome de saída ────────────────────────────
    safe_stem   = _sanitizar_stem(input_path.stem)
    output_path = output_dir / f"{safe_stem}_img.docx"

    # ── [S6] Contenção do output_path dentro do output_dir ───────────
    # Mesmo com stem sanitizado, verificamos explicitamente que o
    # caminho resolvido não escapa do diretório de saída.
    # Protege contra: caller interno comprometido passando output_dir
    # relativo/malicioso (ex: "../uploads", "/tmp/../../etc").
    try:
        output_path.resolve().relative_to(output_dir.resolve())
    except ValueError:
        raise ValueError(
            "Caminho de saída inválido: o arquivo escaparia do diretório permitido."
        )

    # ── [S4] DPI dentro da faixa segura ──────────────────────────────
    safe_dpi = _dpi_seguro(dpi)
    if safe_dpi != dpi:
        log.warning(
            f"[S4] DPI ajustado de {dpi} para {safe_dpi} "
            f"(faixa permitida: {_DPI_MIN}–{_DPI_MAX} DPI)"
        )

    # ── Validação prévia do PDF (páginas, criptografia, integridade) ──
    num_pages = _validar_pdf(input_path)
    log.info(
        f"Iniciando conversão PDF→DOCX (Abordagem 2 — imagem) | "
        f"{num_pages} página(s) | {safe_dpi} DPI"
    )

    pdf_doc = None
    try:
        # [S10] PyMuPDF não executa JavaScript durante get_pixmap().
        #       A renderização em pixels é puramente gráfica — o motor JS
        #       do PDF não é acionado. Seguro para PDFs com JS embutido.
        pdf_doc = fitz.open(str(input_path))

        # ── [S12] Segunda checagem de páginas após fitz.open() ────────────
        # Defesa em profundidade: pypdf e PyMuPDF podem discordar sobre o
        # número real de páginas em PDFs malformados (xrefs corrompidos,
        # object streams aninhados). Se o PDF passou em _validar_pdf() mas
        # o fitz enxerga mais páginas, abortamos aqui antes de renderizar.
        if len(pdf_doc) > MAX_PAGES:
            raise ValueError(
                f"PDF excede o limite de {MAX_PAGES} páginas "
                f"(fitz detectou: {len(pdf_doc)})."
            )
        # ──────────────────────────────────────────────────────────────────

        word_doc = Document()

        # Margens mínimas para maximizar a área útil da imagem na página
        section = word_doc.sections[0]
        margin  = int(914_400 * 0.25)   # 0.25 inch em EMU (English Metric Units)
        section.top_margin    = margin
        section.bottom_margin = margin
        section.left_margin   = margin
        section.right_margin  = margin

        # Largura disponível na página do Word (em EMU)
        page_width_emu = (
            section.page_width - section.left_margin - section.right_margin
        )

        total_bytes = 0  # acumulador para [S6]

        for page_num in range(len(pdf_doc)):
            page = pdf_doc[page_num]

            # ── [S5] Matrix com capping de dimensão ──────────────────
            matrix = _matrix_segura(page, safe_dpi)

            # Renderiza sem canal alpha (economia de ~25% de RAM por página)
            # colorspace=csRGB garante 3 canais mesmo em PDFs com CMYK
            pixmap = page.get_pixmap(
                matrix=matrix,
                alpha=False,
                colorspace=fitz.csRGB,
            )

            # Converte para PNG em memória (sem tocar o disco)
            img_bytes    = pixmap.tobytes("png")
            total_bytes += len(img_bytes)

            # ── [S6] Limite acumulado de saída ────────────────────────
            if total_bytes > _MAX_OUTPUT_BYTES:
                raise ValueError(
                    f"O documento gerado excederia o limite de "
                    f"{_MAX_OUTPUT_BYTES // (1024 * 1024)} MB. "
                    f"Reduza o número de páginas ou utilize DPI menor."
                )

            # ── [S7] Libera memória do pixmap imediatamente ───────────
            #    Sem del explícito, Python acumula TODOS os pixmaps em RAM
            #    até o GC decidir rodar — perigoso com 50 páginas.
            img_stream = io.BytesIO(img_bytes)
            del pixmap, img_bytes   # libera agora, não quando o GC quiser

            # Insere a imagem na largura total da página do Word
            word_doc.add_picture(img_stream, width=page_width_emu)
            img_stream.close()

            # Quebra de página entre páginas (não adiciona após a última)
            if page_num < len(pdf_doc) - 1:
                word_doc.add_page_break()

            log.debug(
                f"  Página {page_num + 1}/{num_pages} OK "
                f"({total_bytes // 1_024} KB acumulados)"
            )

        word_doc.save(str(output_path))

        # ── [S9] Verificação do arquivo final ─────────────────────────
        if not output_path.exists():
            raise FileNotFoundError(
                "python-docx executou sem erro mas o arquivo .docx não foi gerado."
            )

        final_size = output_path.stat().st_size
        if final_size > _MAX_OUTPUT_BYTES:
            output_path.unlink(missing_ok=True)
            raise ValueError(
                f"Arquivo final ({final_size // (1024 * 1024)} MB) excede o limite "
                f"de {_MAX_OUTPUT_BYTES // (1024 * 1024)} MB."
            )

        log.info(
            f"Conversão (Abordagem 2) concluída: {output_path} "
            f"({final_size // 1_024} KB)"
        )
        return str(output_path)

    except Exception as exc:
        # ── [S8] Limpeza do arquivo parcial ──────────────────────────
        #    Previne que um .docx corrompido (incompleto) fique em disco
        #    e seja eventualmente entregue ao usuário ou consuma espaço.
        try:
            if output_path.exists():
                output_path.unlink()
                log.warning(f"[S8] Arquivo parcial removido após erro: {output_path}")
        except Exception:
            pass

        log.error(
            f"Erro na conversão (Abordagem 2) de {input_path}: {exc}",
            exc_info=True,
        )
        raise

    finally:
        # Libera o handle do PyMuPDF SEMPRE — mesmo em erro
        if pdf_doc is not None:
            try:
                pdf_doc.close()
            except Exception:
                pass

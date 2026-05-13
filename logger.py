# logger.py
import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

# Garante que a pasta de logs existe
Path("logs").mkdir(exist_ok=True)

def get_logger(name: str) -> logging.Logger:
    """
    Retorna um logger configurado com saída dupla:
    - Terminal (stdout): para ver em tempo real / journalctl
    - Arquivo rotativo (logs/app.log): histórico persistente
    """
    logger = logging.getLogger(name)

    # Evita adicionar handlers duplicados se a função for chamada várias vezes
    if logger.handlers:
        return logger

    logger.setLevel(logging.DEBUG)

    # Formato completo: data, hora, nível, módulo e mensagem
    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    # --- Handler 1: Terminal ---
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)  # INFO ou acima no terminal
    console_handler.setFormatter(formatter)

    # --- Handler 2: Arquivo rotativo ---
    # maxBytes=5MB, backupCount=3 → guarda até 3 arquivos de 5MB (15MB total)
    file_handler = RotatingFileHandler(
        "logs/app.log",
        maxBytes=5 * 1024 * 1024,
        backupCount=3,
        encoding="utf-8"
    )
    file_handler.setLevel(logging.DEBUG)  # DEBUG ou acima no arquivo
    file_handler.setFormatter(formatter)

    logger.addHandler(console_handler)
    logger.addHandler(file_handler)

    return logger
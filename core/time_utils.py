MILLISECONDS_PER_SECOND = 1000


def seconds_to_milliseconds(seconds: float) -> int:
    """Converte secondi in millisecondi."""
    return round(seconds * MILLISECONDS_PER_SECOND)


def milliseconds_to_seconds(milliseconds: int) -> float:
    """Converte millisecondi in secondi."""
    return milliseconds / MILLISECONDS_PER_SECOND


def format_time(milliseconds: int) -> str:
    """
    Converte millisecondi nel formato HH:MM:SS.mmm.
    """
    total_seconds, ms = divmod(milliseconds, 1000)

    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)

    return f"{hours:02d}:{minutes:02d}:{seconds:02d}.{ms:03d}"
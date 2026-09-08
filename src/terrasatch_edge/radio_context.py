"""Shared physical-channel provenance for continuous and bounded capture."""


def radio_source(base_source: str, channel: int) -> str:
    suffix = f"-radio-bca-ch{channel:02d}"
    prefix = (base_source or "terrasatch-edge").strip() or "terrasatch-edge"
    prefix = prefix[:64 - len(suffix)].rstrip("-_") or "edge"
    return f"{prefix}{suffix}"

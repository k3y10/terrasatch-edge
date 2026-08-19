"""Collect the optional local STT runtime for frozen TerraSatch Edge builds."""

from PyInstaller.utils.hooks import collect_all

_fw_datas, _fw_binaries, _fw_hiddenimports = collect_all("faster_whisper")
_ct_datas, _ct_binaries, _ct_hiddenimports = collect_all("ctranslate2")

datas = _fw_datas + _ct_datas
binaries = _fw_binaries + _ct_binaries
hiddenimports = _fw_hiddenimports + _ct_hiddenimports

import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
collect_ignore = ["windows_original"]   # tests del original (Ollama/tools locales/Windows), fuera de uso (D-004/D-008)

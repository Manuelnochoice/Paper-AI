import importlib, sys, time
print("python", sys.version.split()[0], sys.executable)
for nome in ["numpy", "numpy.random", "pandas", "pyarrow", "pyarrow.lib", "pydantic_core", "fitz", "PIL.Image",
             "altair", "tornado", "streamlit", "yaml", "google.protobuf.internal.api_implementation"]:
    t = time.time()
    try:
        m = importlib.import_module(nome)
        print(f"OK   {nome} {getattr(m, '__version__', '')} ({time.time()-t:.1f}s)")
    except Exception as e:
        print(f"FAIL {nome}: {type(e).__name__}: {str(e)[:150]} ({time.time()-t:.1f}s)")

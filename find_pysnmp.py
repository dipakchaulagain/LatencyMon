import pysnmp
import pkgutil
import sys

def explore_package(package, prefix=""):
    print(f"Exploring {package.__name__}")
    for importer, modname, ispkg in pkgutil.iter_modules(package.__path__):
        full_name = f"{package.__name__}.{modname}"
        try:
            module = __import__(full_name, fromlist="*")
            if hasattr(module, "getCmd") or hasattr(module, "get_cmd"):
                print(f"FOUND getCmd in {full_name}")
            if hasattr(module, "SnmpEngine"):
                print(f"FOUND SnmpEngine in {full_name}")
        except Exception as e:
            pass

explore_package(pysnmp, "pysnmp")
try:
    import pysnmp.hlapi
    explore_package(pysnmp.hlapi, "pysnmp.hlapi")
    import pysnmp.hlapi.asyncio
    explore_package(pysnmp.hlapi.asyncio, "pysnmp.hlapi.asyncio")
except:
    pass

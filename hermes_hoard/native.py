import importlib
from tantalus_hoard.hoard_link.guard import check_request

SPECS = [
    {"id": "products", "name": "Productos y ofertas", "origin": "Tantalus", "description": "Stock, precios, preventas, segunda mano, radar, noticias y ofertas por correo."},
    {"id": "shipments", "name": "Envíos y viajes", "origin": "Phileas", "description": "Correo de seguimiento, transportistas, llegadas, incidencias y planificación de viajes."},
]


def factory(key, data_dir, *, port):
    package = {"products": "tantalus_hoard", "shipments": "phileas_hoard"}[key]
    Config = importlib.import_module(package + ".config").Config
    config = Config.from_env()
    config.data_dir, config.port, config.data_dir_configured = data_dir, port, True
    from tantalus_hoard.hoard_link.appconfig import load_dotenv
    config.secrets.update(load_dotenv(data_dir.parent / ".env"))
    return importlib.import_module(package + ".main").create_app(config)

from tantalus_hoard.hoard_link.copilot import install_copilot

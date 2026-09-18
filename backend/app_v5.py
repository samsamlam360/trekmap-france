"""Point d'entrée TrekMap France 5.0.

Il conserve l'application production existante et ajoute les extensions produit sans
réécrire le backend historique.
"""

from . import main as legacy_main
from .main_production import app, robust_db_or_503
from .product_upgrade import install_product_upgrade

install_product_upgrade(app, legacy_main, robust_db_or_503)

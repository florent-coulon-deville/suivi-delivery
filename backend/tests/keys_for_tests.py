"""La clé de signature des jetons des tests, tirée au hasard une fois par lancement.

À part de conftest.py : pytest charge conftest.py sous deux noms (« conftest » pour ses outils,
« tests.conftest » pour les fichiers de tests qui l'importent), ce qui tirerait deux clés
différentes. Ce fichier-ci n'est chargé qu'une fois (« tests.keys_for_tests »).
"""

from cryptography.hazmat.primitives.asymmetric import rsa

PRIVATE_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)

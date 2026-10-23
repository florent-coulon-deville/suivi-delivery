# Backend (l'API)

```bash
cd backend

uv sync                          # 1. installe Python 3.14 et toutes les dépendances dans .venv/
uv run pytest                    # 2. lance les tests (tous doivent passer)
uv run ruff check .              # 3. vérifie le style et les erreurs courantes
uv run ruff format --check .     # 4. vérifie la mise en forme
uv run ty check                  # 5. vérifie les types
uv run python -m app --reload    # 6. démarre l'API (données en mémoire)
```

Documentation interactive (Swagger) : <http://127.0.0.1:8000/api/docs>

Pour comprendre le code, fichier par fichier : [docs/comprendre-le-code/](../docs/comprendre-le-code/README.md).

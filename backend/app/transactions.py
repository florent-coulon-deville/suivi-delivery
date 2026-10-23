"""Une transaction par requête (stockage SQLite) : tout ce que fait une requête est
enregistré ensemble, ou pas du tout.

Pour chaque appel sous /api :
  1. on ouvre une transaction, qui prend le verrou « une requête à la fois »
     (voir app/storage_sqlite.py) ;
  2. la route travaille ;
  3. juste AVANT d'envoyer la réponse, on enregistre (commit). Le client ne reçoit donc jamais
     un « 201 Créé » pour une donnée qui ne serait pas enregistrée ;
  4. si une erreur imprévue sort de la route (réponse 500), on annule tout.

Une réponse d'erreur prévue (404, 409, 422…) enregistre aussi ce qui a été fait avant elle,
comme le stockage en mémoire. Les saisies incohérentes, elles, sont annulées par l'essai de
app/consistency.py avant même la réponse.

Les probes (/startupz, /readyz, /livez) sont hors de /api : pas de transaction.

C'est un « middleware ASGI » : une fonction placée devant l'application, qui voit passer
chaque requête et chaque morceau de réponse. Les appels à la base, qui font attendre,
sont faits dans un fil d'exécution à part (to_thread) pour ne pas bloquer les autres requêtes.
"""

from anyio import to_thread

from app.storage_sqlite import SESSION, Session, SqliteStorage

READS = {"GET", "HEAD", "OPTIONS"}


class RequestTransaction:
    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send):
        storage = scope["app"].state.storage if scope["type"] == "http" else None
        if not isinstance(storage, SqliteStorage) or not scope["path"].startswith("/api"):
            return await self.app(scope, receive, send)

        session: Session = await to_thread.run_sync(storage.open_session, scope["method"] not in READS)
        token = SESSION.set(session)  # visible de la route, et des fils où elle tourne

        async def wrapped_send(message):
            if message["type"] == "http.response.start":
                await to_thread.run_sync(session.commit)  # sans effet la 2e fois
            await send(message)

        try:
            await self.app(scope, receive, wrapped_send)
        except BaseException:
            await to_thread.run_sync(session.rollback)
            raise
        else:
            await to_thread.run_sync(session.commit)
        finally:
            SESSION.reset(token)

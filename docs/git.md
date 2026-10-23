# Git : branches et ménage

## 1. La façon de travailler

- **`main`** contient la version validée. On ne travaille jamais directement dessus.
- Chaque chantier a **sa branche** (`feat/docker`, `feat/nextjs`…), puis une **pull request (PR)** sur GitHub. La PR est relue, vérifiée par SonarCloud, puis fusionnée dans `main`.
- Les PR sont fusionnées en **squash** (« Squash and merge ») : tous les commits de la branche deviennent **un seul commit** sur `main`, qui porte **le titre de la PR**. `main` garde ainsi une ligne par PR, et chaque PR compte une seule fois dans le journal des versions (avec un commit de fusion, release-please la comptait deux fois).
- **Titre de la PR : Conventional Commits**, car release-please en déduit le prochain numéro de version ([ci.md § 5](ci.md#sortir-une-version--release-please)). Un type, deux-points, puis le texte en français : `feat: export Excel` (nouveauté), `fix(frontend): menu Saisie` (correction), `docs: …`, `ci: …`, `refactor: …`, `chore: …` ; `feat!: …` si l'existant casse. La CI « Titre de la PR » refuse un titre qui ne suit pas la règle ; il suffit de corriger le titre sur GitHub, la vérification se relance. Les messages des commits de la branche, eux, sont libres (ils disparaissent dans le squash). La règle vaut aussi pour le message des petites corrections faites directement sur `main`.

## 2. Après la fusion d'une PR : purger les branches locales

Une fois la PR fusionnée, sa branche ne sert plus. Elle reste pourtant sur votre poste, et parfois sur GitHub. À faire de temps en temps, depuis la racine du projet.

**1. Revenir sur `main` et la mettre à jour.** On ne peut pas supprimer la branche sur laquelle on se trouve.

```bash
git switch main && git pull
```

**2. Oublier les branches supprimées sur GitHub.** Nettoie les références `origin/…` qui n'existent plus ; ne touche pas à vos branches locales.

```bash
git fetch --prune
```

**3. Voir les branches locales dont la branche GitHub a disparu**, sans rien supprimer. Avec le réglage du § 4, GitHub supprime la branche dès que sa PR est fusionnée : `gone` veut donc dire « fusionnée ».

```bash
git branch -vv | grep ': gone]'
```

Avec le squash, Git ne reconnaît plus une branche fusionnée (`git branch --merged` ne la voit pas : son travail est dans `main` sous un autre commit). C'est pourquoi on se fie à la disparition de la branche sur GitHub.

**4. Les supprimer**, après avoir relu la liste de l'étape 3 :

```bash
git branch -vv | grep ': gone]' | awk '{print $1}' | xargs git branch -D
```

`-D` est obligatoire (`-d` répondrait « not fully merged », toujours, à cause du squash). Il supprime sans vérifier : d'où la relecture de l'étape 3. Une branche jamais envoyée sur GitHub n'a pas de `gone` : elle n'est jamais touchée.

**5. Facultatif : supprimer sur GitHub une branche fusionnée qui y est restée.** Elle disparaît pour tout le monde. GitHub peut la restaurer depuis la page de la PR (bouton « Restore branch »).

```bash
git push origin --delete <name-branch>
```

## 3. Les cas particuliers

| Situation | Que faire |
| --- | --- |
| Une branche `gone` dont la PR a été **fermée sans être fusionnée** | Son travail n'est pas dans `main`. Vérifier sur la page de la PR (« Closed », pas « Merged ») avant l'étape 4 ; la garder si besoin (la retirer de la liste). |
| Savoir si une branche a été fusionnée | `gh pr list --state merged --head <branch>` : la PR apparaît si elle a été fusionnée. |
| Jeter volontairement une branche non fusionnée | `git branch -D <branch>` (D majuscule) : **son travail est perdu**, à utiliser en connaissance de cause. |

## 4. Réglages du dépôt GitHub

Dans **Settings**, puis **General**, section « Pull Requests » :

- **Allow squash merging** coché, avec **Default commit message : Pull request title** : le commit sur `main` porte exactement le titre vérifié par la CI ;
- **Allow merge commits** et **Allow rebase merging** décochés : le squash est la seule façon de fusionner ;
- **Automatically delete head branches** coché : GitHub supprime la branche dès que sa PR est fusionnée. Il ne reste que le ménage local (étapes 1 à 4), qui s'appuie justement sur cette suppression.

Dans **Settings**, puis **Rules**, puis **Rulesets** : la règle **« main »** (active, reprise du dépôt SimpleDisenchant, avec le squash) protège `main` :

- interdit de la **supprimer** ou de **réécrire son historique** (`push --force`) ;
- **historique linéaire** (pas de commit de fusion) et **commits signés** (les fusions faites par GitHub le sont d'office ; sur le poste, `git config commit.gpgsign true`) ;
- **passage par une PR**, fusionnée en **squash** seulement, sans relecture obligatoire ;
- **exception pour les administrateurs du dépôt** (« Repository admin », toujours) : les petites corrections peuvent encore être poussées directement sur `main`.

Une règle « tags » (protéger les étiquettes `vX.Y.Z` contre la suppression et la réécriture) existe, **désactivée**.

Dans **Settings**, puis **Advanced Security** (dépôt public : tout est gratuit) :

- **Private vulnerability reporting** : quelqu'un peut signaler une faille en privé ;
- **Dependabot alerts** : alerte quand une bibliothèque utilisée a une faille connue ;
- **Dependabot security updates** : Dependabot ouvre alors une PR qui passe à la version corrigée. Ses PR sont réglées par `.github/dependabot.yml` : titre `fix(deps): …` (Conventional Commits), et **aucune mise à jour ordinaire** (0 PR) : seulement les corrections de sécurité. Les exécutions lancées par Dependabot n'ont pas les secrets du dépôt : `DHI_USERNAME` et `DHI_TOKEN` sont aussi à mettre dans *Secrets and variables* → **Dependabot** (sinon le snapshot de ses branches échoue à la connexion à dhi.io) ;
- **Code scanning** : **CodeQL** (outil de GitHub), en configuration par défaut, analyse notre code (Python, TypeScript, workflows GitHub) à chaque push sur `main` et chaque PR, et chaque semaine ; les rapports **Docker Scout** des images y arrivent aussi ([ci.md § 2](ci.md)) ;
- **Secret Protection** et **Push protection** : détection des secrets poussés, et blocage du push qui en contient un.

Tous les résultats sont dans l'onglet **Security** du dépôt.

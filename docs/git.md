# Git : branches et ménage

## 1. La façon de travailler

- **`main`** contient la version validée. On ne travaille jamais directement dessus.
- Chaque chantier a **sa branche** (`feat/docker`, `feat/nextjs`…), puis une **pull request (PR)** sur GitHub. La PR est relue, vérifiée par SonarCloud, puis fusionnée dans `main`.
- Les PR sont fusionnées avec un **commit de fusion** (« Merge pull request »). Git sait donc reconnaître une branche déjà fusionnée : c'est ce qui permet le ménage ci-dessous.
- **Messages de commit : Conventional Commits**, car release-please en déduit le prochain numéro de version ([ci.md § 5](ci.md#sortir-une-version--release-please)). Un type, deux-points, puis le texte en français : `feat: export Excel` (nouveauté), `fix(frontend): menu Saisie` (correction), `docs: …`, `ci: …`, `refactor: …`, `chore: …` ; `feat!: …` si l'existant casse. Vaut aussi pour les petites corrections faites directement sur `main`. La CI refuse une PR dont un commit ne suit pas la règle. Pour corriger les messages d'une branche :

  ```bash
  git rebase -i origin/main          # remplacer « pick » par « reword » devant chaque commit à renommer
  git push --force-with-lease
  ```

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

**3. Voir les branches locales déjà fusionnées dans `main`**, sans rien supprimer :

```bash
git branch --merged main | grep -vE '^\*|^ *main$'
```

Le `grep` retire de la liste `main` elle-même et la branche en cours (marquée `*`).

**4. Les supprimer :**

```bash
git branch --merged main | grep -vE '^\*|^ *main$' | xargs git branch -d
```

`-d` est la suppression **prudente** : Git refuse de supprimer une branche dont le travail n'est pas dans `main`, avec le message « not fully merged ». Une branche en cours n'est donc jamais perdue.

**5. Facultatif : supprimer sur GitHub une branche fusionnée qui y est restée.** Elle disparaît pour tout le monde. GitHub peut la restaurer depuis la page de la PR (bouton « Restore branch »).

```bash
git push origin --delete <name-branch>
```

## 3. Les cas particuliers

| Situation | Que faire |
| --- | --- |
| `git branch -vv` affiche `[origin/…: gone]` | La branche a été supprimée sur GitHub. Si elle apparaît à l'étape 3, elle est fusionnée : l'étape 4 la supprime. Sinon, son travail n'est pas dans `main` : vérifier avant de la jeter. |
| L'étape 4 refuse une branche (« not fully merged ») | Son travail n'est pas dans `main`. Regarder ce qu'elle contient avec `git log main..<branch>`, puis décider. |
| Jeter volontairement une branche non fusionnée | `git branch -D <branch>` (D majuscule) : **son travail est perdu**, à utiliser en connaissance de cause. |

## 4. Éviter le ménage sur GitHub

Dans les réglages du dépôt GitHub (**Settings**, puis **General**, section « Pull Requests »), cocher **« Automatically delete head branches »**. GitHub supprime alors la branche dès que sa PR est fusionnée. Il ne reste que le ménage local (étapes 1 à 4).

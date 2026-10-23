"use client";
// Gestion des comptes (gardés par Keycloak, gérés ici par l'API), en deux onglets :
//   « Utilisateurs »  les personnes : un mot de passe PROVISOIRE donné par l'administrateur, à
//                     changer à la première connexion ;
//   « Programmes »    scripts, outil de déploiement : une clé générée par l'outil.
//
// La clé d'un programme n'est affichée qu'une fois (à sa création, ou quand on en demande
// une nouvelle) : l'outil ne pourra plus jamais la montrer.
import { useRouter } from "next/navigation";
import { type FormEvent, useCallback, useState } from "react";

import {
  type Changes,
  createAccount,
  updateAccount,
  type NewAccount,
  newKey,
  type Result,
  deleteAccount,
} from "@/app/accounts/actions";
import FilterableList from "@/components/FilterableList";
import Menu from "@/components/Menu";
import ShownSecret from "@/components/ShownSecret";
import Drawer from "@/components/Drawer";
import type { Account } from "@/lib/types";

type Kind = Account["kind"];

const ROLES = [
  ["VIEWER", "Consultation : lire"],
  ["EDITOR", "Saisie : lire, saisir versions, paramètres et installations"],
  ["ADMIN", "Administration : tout, avec la structure et les comptes"],
] as const;

const TABS: { kind: Kind; title: string; help: string; newLabel: string }[] = [
  {
    kind: "PERSON",
    title: "Utilisateurs",
    help: "Les personnes : un mot de passe provisoire, qu'elles changent à leur première connexion.",
    newLabel: "Nouvel utilisateur",
  },
  {
    kind: "PROGRAM",
    title: "Programmes",
    help: "Scripts, outil de déploiement… : ils se connectent avec une clé, générée par l'outil.",
    newLabel: "Nouveau programme",
  },
];

const roleLabel = (role: string | null) => (role ? role.charAt(0) + role.slice(1).toLowerCase() : "Aucun");

type Message = { text: string; error?: boolean };
type Secret = { title: string; value: string };
type Confirmation = { id: string; action: "remove" | "key" };

type Props = { accounts: Account[]; me: string };

export default function AccountManagement({ accounts, me }: Readonly<Props>) {
  const router = useRouter();
  const [kind, setKind] = useState<Kind>("PERSON");
  const [form, setForm] = useState<{ account: Account | null } | null>(null); // null : création
  const [confirmation, setConfirmation] = useState<Confirmation | null>(null);
  const [message, setMessage] = useState<Message | null>(null);
  const [secret, setSecret] = useState<Secret | null>(null);

  const tab = TABS.find((o) => o.kind === kind) ?? (TABS[0] as (typeof TABS)[number]);
  const list = accounts.filter((c) => c.kind === kind);
  const close = useCallback(() => setForm(null), []);

  const changeTab = (newKind: Kind) => {
    setKind(newKind);
    setConfirmation(null);
    setMessage(null);
    setSecret(null);
  };

  const after = (result: Result, text: string, identifier: string) => {
    if (!result.ok) {
      setMessage({ text: result.message, error: true });
      return false;
    }
    // Une clé à noter : l'encadré de la clé suffit, pas besoin de « Enregistré » en plus.
    if (result.key) setSecret({ title: `Clé du programme « ${identifier} »`, value: result.key });
    setMessage(result.key ? null : { text });
    router.refresh();
    return true;
  };

  const confirm = async (account: Account) => {
    const action = confirmation?.action;
    setConfirmation(null);
    if (action === "remove") after(await deleteAccount(account.id), "Supprimé.", account.identifier);
    if (action === "key") after(await newKey(account.id), "Nouvelle clé générée.", account.identifier);
  };

  return (
    <section className="main-card">
      <div className="card-header">
        <div>
          <h2>Comptes</h2>
          <p className="subtitle">{tab.help}</p>
        </div>
        <button type="button" className="button-primary" onClick={() => setForm({ account: null })}>
          + {tab.newLabel}
        </button>
      </div>

      <nav className="sub-tabs">
        {TABS.map((o) => (
          <button
            type="button"
            key={o.kind}
            className={o.kind === kind ? "active" : ""}
            onClick={() => changeTab(o.kind)}
          >
            {o.title}
            <span className="account-menu">{accounts.filter((c) => c.kind === o.kind).length}</span>
          </button>
        ))}
      </nav>

      {secret && <ShownSecret title={secret.title} secret={secret.value} hide={() => setSecret(null)} />}
      {message && (
        <output className={message.error ? "banner error" : "banner success"}>
          {message.error && <strong>Refusé : </strong>}
          {message.text}
        </output>
      )}

      {list.length === 0 ? (
        <div className="empty-state">
          <div className="empty-state-icon">∅</div>
          Aucun compte ici pour l'instant.
        </div>
      ) : (
        <div className="table-container">
          <table className="edit-table">
            <thead>
              <tr>
                <th>Identifiant</th>
                <th>Nom</th>
                <th>Rôle</th>
                <th>Actif</th>
                <th className="col-actions" />
              </tr>
            </thead>
            <tbody>
              {list.map((c) => (
                <tr key={c.id}>
                  <td>
                    <code>{c.identifier}</code>
                    {c.identifier === me && <span className="bullet">vous</span>}
                  </td>
                  <td>{c.name}</td>
                  <td>{roleLabel(c.role)}</td>
                  <td>{c.active ? "oui" : "non"}</td>
                  <td className="col-actions">
                    <AccountActions
                      account={c}
                      confirmation={confirmation}
                      ask={setConfirmation}
                      confirm={confirm}
                      update={() => setForm({ account: c })}
                    />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {form && (
        <Drawer close={close} title="Compte">
          <header className="panel-header">
            <div>
              <div className="panel-overline">{tab.title}</div>
              <h2>{form.account ? `Modifier ${form.account.identifier}` : tab.newLabel}</h2>
            </div>
            <button type="button" className="close" onClick={close} aria-label="Fermer">
              ✕
            </button>
          </header>
          <div className="panel-body">
            <AccountForm
              key={form.account?.id ?? `new-${kind}`}
              account={form.account}
              kind={kind}
              cancel={close}
              finish={(result, identifier) => {
                if (after(result, "Enregistré.", identifier)) setForm(null);
                return result.ok ? null : result.message;
              }}
            />
          </div>
        </Drawer>
      )}

    </section>
  );
}

type PropsActions = {
  account: Account;
  confirmation: Confirmation | null;
  ask: (confirmation: Confirmation | null) => void;
  confirm: (account: Account) => void;
  update: () => void;
};

// Actions d'une ligne, regroupées dans un menu « ⋯ » ; une suppression ou une nouvelle clé
// demande confirmation (Oui en rouge, Non) à la place du menu.
function AccountActions({ account, confirmation, ask, confirm, update }: Readonly<PropsActions>) {
  if (confirmation?.id === account.id) {
    return (
      <span className="confirmation button-group">
        {confirmation.action === "remove" ? "Supprimer ?" : "Remplacer la clé ?"}
        <button type="button" className="button-danger" onClick={() => confirm(account)}>
          Oui
        </button>
        <button type="button" className="button-secondary" onClick={() => ask(null)}>
          Non
        </button>
      </span>
    );
  }
  return (
    <Menu label="⋯" title={`Actions sur ${account.identifier}`} className="button-secondary button-icon">
      <button type="button" className="menu-element" onClick={update}>
        Modifier
      </button>
      {account.kind === "PROGRAM" && (
        <button type="button" className="menu-element" onClick={() => ask({ id: account.id, action: "key" })}>
          Nouvelle clé
        </button>
      )}
      <div className="menu-separator" />
      <button
        type="button"
        className="menu-element danger"
        onClick={() => ask({ id: account.id, action: "remove" })}
      >
        Supprimer
      </button>
    </Menu>
  );
}

type FormProps = {
  account: Account | null;
  kind: Kind; // celle de l'onglet : fixée à la création
  cancel: () => void;
  finish: (result: Result, identifier: string) => string | null; // message d'erreur, ou null
};

function AccountForm({ account, kind, cancel, finish }: Readonly<FormProps>) {
  const [identifier, setIdentifier] = useState(account?.identifier ?? "");
  const [name, setName] = useState(account?.name ?? "");
  const [role, setRole] = useState<string>(account?.role ?? "VIEWER");
  const [active, setActive] = useState(account?.active ?? true);
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [sending, setSending] = useState(false);

  const person = (account?.kind ?? kind) === "PERSON";
  const buttonLabel = account ? "Enregistrer" : "Créer";

  const validate = async (e: FormEvent) => {
    e.preventDefault();
    setSending(true);
    setError(null);
    let result: Result;
    if (account) {
      const changes: Changes = { name, role, active };
      if (password) changes.password = password;
      result = await updateAccount(account.id, changes);
    } else {
      const created: NewAccount = { identifier, name, kind, role };
      if (person) created.password = password;
      result = await createAccount(created);
    }
    setSending(false);
    setError(finish(result, account?.identifier ?? identifier));
  };

  return (
    <form className="form" onSubmit={validate}>
      {error && (
        <div className="form-alert" role="alert">
          <strong>Refusé :</strong> {error}
        </div>
      )}
      {!account && (
        <div className="field">
          <label htmlFor="c-identifier">
            Identifiant<span className="required"> *</span>
          </label>
          <input id="c-identifier" value={identifier} required onChange={(e) => setIdentifier(e.target.value)} />
          <div className="field-help">Lettres, chiffres, - et _ ; ne se modifie plus ensuite.</div>
        </div>
      )}
      <div className="field">
        <label htmlFor="c-name">
          Nom<span className="required"> *</span>
        </label>
        <input id="c-name" value={name} required onChange={(e) => setName(e.target.value)} />
      </div>
      <div className="field">
        <label htmlFor="c-role">Rôle</label>
        <FilterableList
          id="c-role"
          value={role}
          required
          change={setRole}
          options={ROLES.map(([value, text]) => ({ value, text }))}
        />
      </div>
      {person && (
        <div className="field">
          <label htmlFor="c-password">
            {account ? "Nouveau mot de passe provisoire" : "Mot de passe provisoire"}
            {!account && <span className="required"> *</span>}
          </label>
          <input
            id="c-password"
            type="password"
            autoComplete="new-password"
            value={password}
            required={!account}
            minLength={12}
            onChange={(e) => setPassword(e.target.value)}
          />
          <div className="field-help">
            12 caractères au moins, différent de l'identifiant. La personne en choisira un nouveau à sa
            prochaine connexion.
            {account && " Vide : inchangé. Un nouveau mot de passe met fin à ses connexions en cours."}
          </div>
        </div>
      )}
      {!person && !account && (
        <div className="field-help">La clé du programme sera affichée une seule fois, après la création.</div>
      )}
      {account && (
        <label className="field checkbox-field">
          <input type="checkbox" checked={active} onChange={(e) => setActive(e.target.checked)} />
          <span>Actif (décoché : ne peut plus se connecter, ses scripts non plus)</span>
        </label>
      )}
      <div className="form-actions">
        <button type="button" className="button-secondary" onClick={cancel}>
          Annuler
        </button>
        <button type="submit" className="button-primary" disabled={sending}>
          {sending ? "Enregistrement…" : buttonLabel}
        </button>
      </div>
    </form>
  );
}

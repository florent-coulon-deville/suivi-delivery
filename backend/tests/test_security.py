"""Vérification des jetons de Keycloak (app/security.py) : signature, émetteur, destinataire, expiration."""

import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from app.schemas import AccountKind, Role
from app.security import Identity, InvalidToken, has_role, strongest_role, token_identity
from tests.conftest import sign, token_content, verifier


def test_identity_of_a_person():
    identity = verifier().check(sign(token_content("paul", Role.EDITOR, name="Paul Martin", subject="s1")))
    assert identity == Identity(
        subject="s1", identifier="paul", name="Paul Martin", kind=AccountKind.PERSON, role=Role.EDITOR
    )


def test_identity_of_a_program():
    identity = token_identity(token_content("tool", Role.VIEWER, AccountKind.PROGRAM))
    assert (identity.identifier, identity.kind) == ("tool", AccountKind.PROGRAM)


@pytest.mark.parametrize(
    ("roles", "expected"),
    [
        (["VIEWER", "EDITOR", "ADMIN"], Role.ADMIN),  # composites de Keycloak
        (["offline_access", "EDITOR"], Role.EDITOR),
        (["offline_access", "uma_authorization"], None),
        ([], None),
    ],
)
def test_strongest_role(roles, expected):
    assert strongest_role(roles) == expected


def test_without_role_nothing_is_allowed():
    identity = token_identity(token_content("paul", None))
    assert identity.role is None
    assert not has_role(identity, Role.VIEWER)


@pytest.mark.parametrize(
    "change",
    [
        {"exp": 1},  # expiré
        {"iss": "http://other-keycloak/auth/realms/suivi-delivery"},  # autre émetteur
        {"aud": ["account"]},  # pas fait pour l'API de l'outil
        {"typ": "ID"},  # un jeton d'identité, pas d'accès
    ],
)
def test_rejected_tokens(change):
    token = sign({**token_content("paul", Role.EDITOR), **change})
    check = verifier().check
    with pytest.raises(InvalidToken):
        check(token)


def test_signature_from_another_key_rejected():
    other_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    token = sign(token_content("paul", Role.EDITOR), key=other_key)
    check = verifier().check
    with pytest.raises(InvalidToken):
        check(token)


def test_unreadable_or_unsigned_token_rejected():
    check = verifier().check
    for token in ("not-a-token", sign(token_content("paul", Role.EDITOR))[:-5] + "abcde"):
        with pytest.raises(InvalidToken):
            check(token)


def test_rejected_token_401(anonymous):
    content = {**token_content("admin", Role.ADMIN), "exp": 1}
    response = anonymous.get("/api/me", headers={"Authorization": f"Bearer {sign(content)}"})
    assert response.status_code == 401
    assert response.json()["detail"] == "Jeton d'accès invalide ou expiré"

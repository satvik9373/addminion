from datetime import datetime, timedelta, timezone

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa

from application.auth import SupabaseAuthAdapter, SupabaseJWTVerifier


class StaticKey:
    def __init__(self, key):
        self.key = key


class StaticKeyClient:
    def __init__(self, key):
        self.key = key

    def get_signing_key_from_jwt(self, _token):
        return StaticKey(self.key)


def _tokens(**overrides):
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    now = datetime.now(timezone.utc)
    claims = {
        'sub': 'subject-1',
        'email': 'owner@example.com',
        'iat': now,
        'exp': now + timedelta(minutes=5),
        'iss': 'https://project.supabase.co/auth/v1',
        'aud': 'authenticated',
    }
    claims.update(overrides)
    token = jwt.encode(claims, private_key, algorithm='RS256')
    return token, private_key.public_key()


def _adapter(**overrides):
    token, public_key = _tokens(**overrides)
    verifier = SupabaseJWTVerifier(
        'https://project.supabase.co',
        key_client=StaticKeyClient(public_key),
    )
    return token, SupabaseAuthAdapter(verifier)


def test_valid_supabase_jwt_is_verified_and_mapped():
    token, adapter = _adapter()

    identity = adapter.authenticate(token)

    assert identity is not None
    assert identity.subject == 'subject-1'
    assert identity.email == 'owner@example.com'


def test_invalid_signature_is_rejected():
    token, adapter = _adapter()
    other_private = rsa.generate_private_key(
        public_exponent=65537, key_size=2048)
    invalid = jwt.encode(
        jwt.decode(token, options={'verify_signature': False}),
        other_private,
        algorithm='RS256',
    )

    assert adapter.authenticate(invalid) is None


def test_expired_issuer_and_audience_tokens_are_rejected():
    for claims in (
        {'exp': datetime.now(timezone.utc) - timedelta(minutes=1)},
        {'iss': 'https://wrong.example/auth/v1'},
        {'aud': 'wrong-audience'},
    ):
        token, adapter = _adapter(**claims)
        assert adapter.authenticate(token) is None


def test_malformed_and_missing_tokens_are_rejected():
    _, adapter = _adapter()

    assert adapter.authenticate(None) is None
    assert adapter.authenticate('not-a-jwt') is None

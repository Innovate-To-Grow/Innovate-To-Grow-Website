from i2g_admin.pkce import challenge_s256, generate_verifier

# RFC 7636 Appendix B reference vector — shared with the backend's verify_pkce_s256 test.
RFC_VERIFIER = "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk"
RFC_CHALLENGE = "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM"


def test_known_vector():
    assert challenge_s256(RFC_VERIFIER) == RFC_CHALLENGE


def test_generate_verifier_in_range():
    verifier = generate_verifier()
    assert 43 <= len(verifier) <= 128


def test_roundtrip_challenge_length():
    challenge = challenge_s256(generate_verifier())
    assert 43 <= len(challenge) <= 128
    assert "=" not in challenge

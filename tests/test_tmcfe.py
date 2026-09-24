import pytest

from crosfed.crypto import TMCFEError, ThresholdMCFE


@pytest.fixture()
def fixture_data():
    vectors = [[3, -2, 5], [-1, 4, 2], [2, 1, -4]]
    weights = [[1, 1, 1], [2, 2, 2], [1, 1, 1]]
    scheme = ThresholdMCFE("SS512")
    scheme.setup(3, 3)
    keys = scheme.generate_functional_keys(weights, [1, 2, 3], 2, 7)
    ciphertexts = [scheme.encrypt(x, scheme.encryption_key(i + 1), 7) for i, x in enumerate(vectors)]
    shares = [scheme.share_decrypt(ciphertexts, weights, keys[j], [1, 3], 7) for j in [1, 3]]
    return scheme, vectors, weights, keys, ciphertexts, shares


def test_exact_weighted_sum(fixture_data) -> None:
    scheme, vectors, weights, _, _, shares = fixture_data
    expected = [sum(vectors[i][z] * weights[i][z] for i in range(3)) for z in range(3)]
    assert scheme.combine(shares, 7, 64) == expected


def test_adjacent_committee_ids_interpolate_correctly(fixture_data) -> None:
    scheme, vectors, weights, keys, ciphertexts, _ = fixture_data
    shares = [
        scheme.share_decrypt(ciphertexts, weights, keys[j], [1, 2], 7)
        for j in [1, 2]
    ]
    expected = [sum(vectors[i][z] * weights[i][z] for i in range(3)) for z in range(3)]
    assert scheme.combine(shares, 7, 64) == expected


def test_rejects_insufficient_replayed_and_tampered_shares(fixture_data) -> None:
    scheme, _, weights, keys, ciphertexts, shares = fixture_data
    with pytest.raises(TMCFEError, match="insufficient"):
        scheme.combine(shares[:1], 7, 64)
    with pytest.raises(TMCFEError, match="round mismatch"):
        scheme.share_decrypt(ciphertexts, weights, keys[1], [1, 3], 8)
    with pytest.raises(TMCFEError, match="inconsistent"):
        scheme.combine([shares[0], scheme.tamper_numerator(shares[1])], 7, 64)
    with pytest.raises(TMCFEError, match="duplicate"):
        scheme.combine([shares[0], shares[0]], 7, 64)
    malicious_weights = [row[:] for row in weights]
    malicious_weights[0][0] = 0
    with pytest.raises(TMCFEError, match="function/weight mismatch"):
        scheme.share_decrypt(ciphertexts, malicious_weights, keys[1], [1, 3], 7)


def test_ciphertext_and_share_payload_roundtrip(fixture_data) -> None:
    scheme, _, _, _, ciphertexts, shares = fixture_data
    ciphertext = scheme.ciphertext_from_payload(scheme.ciphertext_to_payload(ciphertexts[0]))
    share = scheme.partial_share_from_payload(scheme.partial_share_to_payload(shares[0]))
    assert ciphertext.client_id == ciphertexts[0].client_id
    assert ciphertext.round_id == ciphertexts[0].round_id
    assert [scheme.pp.group.serialize(item) for item in ciphertext.ct0] == [
        scheme.pp.group.serialize(item) for item in ciphertexts[0].ct0
    ]
    assert share.aggregator_id == shares[0].aggregator_id
    assert share.committee == shares[0].committee
    assert [scheme.pp.group.serialize(item) for item in share.numerator] == [
        scheme.pp.group.serialize(item) for item in shares[0].numerator
    ]


@pytest.mark.parametrize("exponent", [-12_345, -1, 0, 42, 98_765])
def test_diagnostic_bsgs_recovers_signed_exponent(fixture_data, exponent: int) -> None:
    scheme, *_ = fixture_data
    element = scheme.pp.generator ** scheme._zr(exponent)
    assert scheme._bounded_dlog_bsgs(element, 100_000) == exponent


def test_arithmetic_identity_is_recognized(fixture_data) -> None:
    scheme, *_ = fixture_data
    value = scheme.pp.generator ** scheme._zr(12_345)
    arithmetic_identity = value / value
    direct_identity = scheme.pp.generator ** scheme._zr(0)
    assert arithmetic_identity == direct_identity
    assert scheme._bounded_dlog_bsgs(arithmetic_identity, 100) == 0

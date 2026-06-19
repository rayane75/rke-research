"""Vérifie l'AES-128 contre le vecteur officiel FIPS-197, plus l'avalanche."""

from __future__ import annotations

from rke import aes128


def hamming(a: bytes, b: bytes) -> int:
    return sum(bin(x ^ y).count("1") for x, y in zip(a, b))


def test_fips197_known_answer():
    key = bytes.fromhex("000102030405060708090a0b0c0d0e0f")
    plain = bytes.fromhex("00112233445566778899aabbccddeeff")
    expected = bytes.fromhex("69c4e0d86a7b0430d8cdb78070b4c55a")
    assert aes128.encrypt_block(plain, key) == expected


def test_avalanche_one_bit_input_flips_about_half_output():
    key = bytes.fromhex("2b7e151628aed2a6abf7158809cf4f3c")
    c0 = aes128.encrypt_block((0).to_bytes(16, "big"), key)
    c1 = aes128.encrypt_block((1).to_bytes(16, "big"), key)
    flipped = hamming(c0, c1)
    # +1 sur l'entrée => ~64 bits sur 128 changent (avalanche). Bande large.
    assert 45 <= flipped <= 83, flipped

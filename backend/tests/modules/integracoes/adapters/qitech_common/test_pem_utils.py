"""PEM loading — accept P-521, reject everything else."""

from __future__ import annotations

import pytest

from app.modules.integracoes.adapters._qitech_common.errors import QiTechSigningError
from app.modules.integracoes.adapters._qitech_common.pem_utils import (
    load_private_key,
    load_public_key,
)
from tests.modules.integracoes.adapters.qitech_common._fixtures import (
    PRIVATE_PEM_P256_WRONG_CURVE,
    PRIVATE_PEM_P521,
    PUBLIC_PEM_P521,
)


def test_load_private_key_accepts_p521() -> None:
    key = load_private_key(PRIVATE_PEM_P521)
    assert key.curve.name == "secp521r1"


def test_load_public_key_accepts_p521() -> None:
    key = load_public_key(PUBLIC_PEM_P521)
    assert key.curve.name == "secp521r1"


def test_load_private_key_rejects_wrong_curve() -> None:
    with pytest.raises(QiTechSigningError, match="P-521"):
        load_private_key(PRIVATE_PEM_P256_WRONG_CURVE)


def test_load_private_key_rejects_garbage() -> None:
    with pytest.raises(QiTechSigningError, match="invalid private PEM"):
        load_private_key("not a pem")


def test_load_public_key_rejects_garbage() -> None:
    with pytest.raises(QiTechSigningError, match="invalid public PEM"):
        load_public_key("-----BEGIN PUBLIC KEY-----\nnope\n-----END PUBLIC KEY-----\n")


def test_load_private_key_accepts_bytes_input() -> None:
    key = load_private_key(PRIVATE_PEM_P521.encode("utf-8"))  # type: ignore[arg-type]
    assert key.curve.name == "secp521r1"

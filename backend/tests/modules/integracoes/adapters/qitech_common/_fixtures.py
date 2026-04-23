"""Test keypairs for the QiTech primitives.

Generated once with `cryptography` and hard-coded here. These are ONLY used
by tests; they never touch production code paths.

DO NOT use these keys to sign anything besides test vectors.
"""

from __future__ import annotations

# ES512 / P-521 — the curve QiTech requires for real requests.
PRIVATE_PEM_P521 = """-----BEGIN PRIVATE KEY-----
MIHuAgEAMBAGByqGSM49AgEGBSuBBAAjBIHWMIHTAgEBBEIBsa5wPG+Z/I3+fw2W
cBAPDiLZaAzQIFy5Q/LmWMKiinBaAYpL1JKGb3nwhior3dI4iuCt7fqIRCxQkReS
U8ZqzW2hgYkDgYYABAA1p3RHjlecD57qYHas37z3I5ehO58qUtrBi306iOmPnEL4
Dg5Typ9IMbaUjlCPsYNFlFt2AKwH8bDLFwGUoICmSQEEDJwZR56p0O4JssjZ7I7N
F5olwo+1ZxVf1ZzfABLxotJx6ZVJ3F9ySwsRaw5ltngNk12Wp5p2TjMFO82GZ1me
cA==
-----END PRIVATE KEY-----
"""

PUBLIC_PEM_P521 = """-----BEGIN PUBLIC KEY-----
MIGbMBAGByqGSM49AgEGBSuBBAAjA4GGAAQANad0R45XnA+e6mB2rN+89yOXoTuf
KlLawYt9Oojpj5xC+A4OU8qfSDG2lI5Qj7GDRZRbdgCsB/GwyxcBlKCApkkBBAyc
GUeeqdDuCbLI2eyOzReaJcKPtWcVX9Wc3wAS8aLScemVSdxfcksLEWsOZbZ4DZNd
lqeadk4zBTvNhmdZnnA=
-----END PUBLIC KEY-----
"""

# P-256 — wrong curve; used only in negative tests.
PRIVATE_PEM_P256_WRONG_CURVE = """-----BEGIN PRIVATE KEY-----
MIGHAgEAMBMGByqGSM49AgEGCCqGSM49AwEHBG0wawIBAQQg0lgExhrBzy/bcngI
Cf/EbzC3PLducL2aygi3OaNi3t+hRANCAAQGhdg42I3Wo3ssY5f9xfib5oItS2Yo
JN8ve3YHbwIyYjIxDO6Pb2n07kjaZ85IXjZoFFlpF0h3D8YW2mPaMpbd
-----END PRIVATE KEY-----
"""

API_CLIENT_KEY = "11111111-2222-3333-4444-555555555555"

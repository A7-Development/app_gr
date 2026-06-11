"""Adapter Infosimples — consultas governamentais (JUCESP fase 1).

Um adapter por API/consulta-família (§13). Credencial global cifrada em
`provedor_dados_credencial`; logins por família (jucesp, protesto) no mesmo
secret. Output em modelo canônico via mappers; bronze em
`wh_infosimples_raw_consulta`.
"""

from app.modules.integracoes.adapters.data.infosimples.client import (  # noqa: F401
    InfosimplesResponse,
    build_async_client,
    consulta,
    download_binary,
)
from app.modules.integracoes.adapters.data.infosimples.config import (  # noqa: F401
    InfosimplesConfig,
)
from app.modules.integracoes.adapters.data.infosimples.version import (  # noqa: F401
    ADAPTER_VERSION,
)

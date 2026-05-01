"""Bureau adapters — consultas pontuais a fontes externas pagas.

Diferente dos adapters `erp/` e `admin/`, que sao **sync periodico** (ETL
orquestrado por sync_runner), bureau adapters sao **query sob demanda**:
dado um CNPJ ou CPF, dispara uma chamada e retorna o relatorio.

Quem grava raw + chama mapper + grava silver e o caller (BureauQueryNode
no workflow do credito, ou um service do dominio). O adapter em si retorna
o payload bruto + metadados de proveniencia — nao toca em DB do GR.

Adapters em construcao:
    serasa_pj/   — Business Information Report (CNPJ)
    serasa_pf/   — Person Information Report (CPF)
"""

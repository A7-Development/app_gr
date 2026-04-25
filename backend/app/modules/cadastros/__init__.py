"""Cadastros -- entidades de dominio do tenant (CLAUDE.md secao 11.1).

Cobre as entidades primarias que pertencem ao tenant e independem de fonte
externa. Primeira entrega (Sprint UA): Unidade Administrativa -- FIDCs,
securitizadoras, gestoras, factorings, consultorias.

UA primaria (este modulo) vs UA do Bitfin (warehouse):

    cadastros.UnidadeAdministrativa     -> cadastro primario do tenant
                                           (editavel via UI, fonte da verdade
                                           de quais UAs existem no sistema).

    wh_dim_unidade_administrativa       -> espelho populado pelo ETL Bitfin
                                           (estrutura interna do ERP, com
                                           proveniencia Auditable).

Vinculo: `UnidadeAdministrativa.bitfin_ua_id` (nullable) liga a UA primaria
ao registro espelho. Nem toda UA primaria tem vinculo (pode ser uma UA
gerenciada apenas via QiTech ou outra admin). Nem todo registro espelho do
Bitfin tem UA primaria correspondente -- ETL roda; cadastro vem depois.
"""

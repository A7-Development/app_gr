-- Seed/curadoria dos datasets BDC do v1 da esteira de credito (decisao 2026-06-16).
-- Cura a CAMADA A7 (public_code, query_name, display_name, categoria, enabled)
-- das linhas ja sincronizadas por /precos/ em provedor_dados_dataset. Precos
-- (current_cost_brl / pricing_tiers_json) ja vem do sync — nao tocamos aqui.
--
-- Idempotente (UPDATE por billing_code + api). Aplicado em gr_db via MCP
-- (heads alembic divergentes -> nao roda por alembic upgrade). Espelha
-- scripts/seed_central_dados_cadpj.sql.
--
-- GOTCHA: provider_dataset_code NAO e unico entre APIs (KYC_V1/REGISTRATION_DATA_V1/
-- BASIC_DATA_V1 existem em People/Lawsuits/etc.). O filtro provider_api='Companies'
-- + provider_id e OBRIGATORIO pra nao curar a linha errada.
--
-- Pacotes v1:
--   Cadastral        : basic_data (CAD-PJ, ja curado), registration_data, activity_indicators
--   Quadro Societario: dynamic_qsa_data, relationships, economic_group_first_level
--   KYC da empresa   : kyc
--   (v1.5, seedado disponivel) : owners_kyc  -- KYC dos socios; BDC faz fan-out a partir do CNPJ
--
-- basic_data/CAD-PJ ja esta curado e enabled (nao re-seedado aqui).

UPDATE provedor_dados_dataset d
SET public_code         = m.public_code,
    provider_query_name = m.query_name,
    display_name_pt_br  = m.display_name,
    categoria_ui        = 'empresas',
    enabled_for_sale    = true
FROM (VALUES
  ('REGISTRATION_DATA_V1',          'CONTATO-PJ',    'registration_data',          'Contatos PJ'),
  ('ACTIVITY_INDICATORS_V1',        'ATIVIDADE-PJ',  'activity_indicators',        'Indicadores de Atividade PJ'),
  ('DYNAMIC_QSA_DATA_V1',           'QSA-PJ',        'dynamic_qsa_data',           'Quadro Societario PJ'),
  ('RELATIONSHIPS_V1',              'VINCULOS-PJ',   'relationships',              'Vinculos da Empresa'),
  ('ECONOMIC_GROUP_FIRST_LEVEL_V1', 'GRUPO-PJ',      'economic_group_first_level', 'Grupo Economico (1o nivel)'),
  ('KYC_V1',                        'KYC-PJ',        'kyc',                        'KYC da Empresa'),
  ('OWNERS_KYC_V1',                 'KYC-SOCIOS-PJ', 'owners_kyc',                 'KYC dos Socios')
) AS m(billing_code, public_code, query_name, display_name)
WHERE d.provider_dataset_code = m.billing_code
  AND d.provider_api = 'Companies'
  -- GOTCHA: coluna slug guarda o NOME do enum (UPPERCASE), nao o value.
  -- 'bigdatacorp' (lowercase) nao casa -> usar 'BIGDATACORP' ou o id fixo.
  AND d.provider_id = (SELECT id FROM provedor_dados WHERE slug = 'BIGDATACORP');

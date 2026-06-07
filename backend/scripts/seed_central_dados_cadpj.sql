-- Seed da Central de Dados — glossário + produto CAD-PJ + ligação de campos.
-- Idempotente (ON CONFLICT DO NOTHING / UPDATE). Aplicado em gr_db via MCP em
-- 2026-06-07 (heads alembic divergentes -> não roda por alembic upgrade).
-- Ver docs/central-de-dados-arquitetura.md §4/§5.

-- 1) Termos canônicos (glossário, global)
INSERT INTO termo_canonico (codigo, nome_pt_br, descricao, tipo_semantico, sensibilidade_default, unidade) VALUES
 ('CNPJ', 'CNPJ', 'Número de inscrição no CNPJ (14 dígitos).', 'cnpj', 'publico', NULL),
 ('RAZAO_SOCIAL', 'Razão social', 'Nome empresarial oficial da PJ.', 'text', 'publico', NULL),
 ('NOME_FANTASIA', 'Nome fantasia', 'Nome de fantasia / nome comercial.', 'text', 'publico', NULL),
 ('SITUACAO_CADASTRAL', 'Situação cadastral', 'Situação do CNPJ na Receita (ativa, baixada, etc.).', 'enum', 'publico', NULL),
 ('DATA_FUNDACAO', 'Data de fundação', 'Data de abertura/constituição da empresa.', 'date', 'publico', NULL),
 ('CAPITAL_SOCIAL', 'Capital social', 'Capital social declarado, em reais.', 'money', 'publico', 'BRL'),
 ('CNAE', 'CNAE', 'Código(s) CNAE de atividade econômica.', 'cnae', 'publico', NULL),
 ('NATUREZA_JURIDICA', 'Natureza jurídica', 'Natureza jurídica (ex.: Sociedade Limitada).', 'text', 'publico', NULL),
 ('UF', 'UF', 'Unidade federativa da matriz.', 'text', 'publico', NULL),
 ('REGIME_TRIBUTARIO', 'Regime tributário', 'Regime tributário declarado.', 'text', 'publico', NULL),
 ('IDADE_EMPRESA', 'Idade da empresa', 'Idade da empresa em anos.', 'number', 'publico', 'anos'),
 ('OPTANTE_SIMPLES', 'Optante pelo Simples', 'Se a empresa é optante pelo Simples Nacional.', 'bool', 'publico', NULL)
ON CONFLICT (codigo) DO NOTHING;

-- 2) Produto de Dado lógico CAD-PJ + origem BDC
INSERT INTO produto_dado (public_code, nome_pt_br, descricao, categoria, silver_target, tenant_id) VALUES
 ('CAD-PJ', 'Cadastro PJ', 'Dados cadastrais de uma pessoa jurídica (CNPJ): razão social, situação, CNAE, fundação, capital.', 'cadastro', 'wh_pj_cadastro', NULL)
ON CONFLICT (public_code) DO NOTHING;

INSERT INTO produto_dado_origem (produto_id, provider, api_endpoint, dataset_code, prioridade, ativo)
SELECT p.id, 'bdc', 'empresas', 'basic_data', 1, true
FROM produto_dado p WHERE p.public_code = 'CAD-PJ'
ON CONFLICT (produto_id, provider, api_endpoint, dataset_code) DO NOTHING;

-- 3) Liga campos do contrato CAD-PJ ativo aos termos canônicos
UPDATE dataset_field df
SET termo_canonico_id = t.id
FROM (VALUES
  ('TaxIdNumber','CNPJ'), ('OfficialName','RAZAO_SOCIAL'), ('TradeName','NOME_FANTASIA'),
  ('TaxIdStatus','SITUACAO_CADASTRAL'), ('FoundedDate','DATA_FUNDACAO'),
  ('AdditionalOutputData.CapitalRS','CAPITAL_SOCIAL'), ('Activities[].Code','CNAE'),
  ('LegalNature.Activity','NATUREZA_JURIDICA'), ('HeadquarterState','UF'),
  ('TaxRegime','REGIME_TRIBUTARIO'), ('Age','IDADE_EMPRESA'), ('TaxRegimes.Simples','OPTANTE_SIMPLES')
) AS m(field_path, codigo)
JOIN termo_canonico t ON t.codigo = m.codigo
WHERE df.field_path = m.field_path
  AND df.contract_id = (SELECT a.active_contract_id FROM dataset_contract_active a
      JOIN dataset_contract dc ON dc.id = a.active_contract_id
      WHERE dc.public_code='CAD-PJ' AND a.tenant_id IS NULL);

-- 4) Promove identidade ao silver + corrige silver_target p/ nomes canônicos
UPDATE dataset_field df
SET to_silver = true, silver_target = m.tgt
FROM (VALUES
  ('TaxIdNumber','cnpj'), ('OfficialName','razao_social'), ('TradeName','nome_fantasia'),
  ('TaxIdStatus','situacao_cadastral'), ('FoundedDate','data_fundacao')
) AS m(field_path, tgt)
WHERE df.field_path = m.field_path
  AND df.contract_id = (SELECT a.active_contract_id FROM dataset_contract_active a
      JOIN dataset_contract dc ON dc.id = a.active_contract_id
      WHERE dc.public_code='CAD-PJ' AND a.tenant_id IS NULL);

"""Unit tests — app/shared/documento.py (identity policy primitives).

Sem CPF real de producao aqui (PII): CPFs sao os exemplos sinteticos
classicos de validacao; CNPJs sao publicos (Banco do Brasil) ou o exemplo
canonico de documentacao 11.444.777/0001-61.
"""

from app.core.enums import TipoPessoa
from app.shared.documento import normalizar_documento

# CNPJ matriz/filial do exemplo canonico de documentacao (DVs reais).
CNPJ_MATRIZ = "11444777000161"
CNPJ_FILIAL_2 = "11444777000242"
# Banco do Brasil — raiz toda zero (caso que proibe lstrip de zeros).
CNPJ_BB = "00000000000191"
CPF_VALIDO = "52998224725"


class TestCnpj:
    def test_cnpj_14_digitos_valido(self):
        d = normalizar_documento(CNPJ_MATRIZ, TipoPessoa.PJ)
        assert d is not None
        assert d.documento == CNPJ_MATRIZ
        assert d.tipo_pessoa == TipoPessoa.PJ
        assert d.valido is True
        assert d.raiz == "11444777"
        assert d.filial_numero == "0001"
        assert d.is_matriz is True

    def test_filial_compartilha_raiz_e_nao_e_matriz(self):
        d = normalizar_documento(CNPJ_FILIAL_2, TipoPessoa.PJ)
        assert d is not None and d.valido
        assert d.raiz == "11444777"
        assert d.filial_numero == "0002"
        assert d.is_matriz is False

    def test_bitfin_padding_15_chars(self):
        """Bitfin armazena PJ zero-padded a 15 chars — rightmost 14 valem."""
        d = normalizar_documento("0" + CNPJ_BB, TipoPessoa.PJ)
        assert d is not None
        assert d.documento == CNPJ_BB
        assert d.valido is True
        assert d.raiz == "00000000"
        assert d.is_matriz is True

    def test_padding_com_lixo_na_frente_e_invalido(self):
        """15 digitos cujo excedente NAO e zero nao cabem em CNPJ."""
        assert normalizar_documento("9" + CNPJ_BB, TipoPessoa.PJ) is None

    def test_mascara_e_aceita(self):
        d = normalizar_documento("11.444.777/0001-61", TipoPessoa.PJ)
        assert d is not None and d.documento == CNPJ_MATRIZ and d.valido

    def test_check_digit_errado_retorna_invalido_mas_com_forma(self):
        d = normalizar_documento("11444777000160", TipoPessoa.PJ)
        assert d is not None
        assert d.valido is False
        assert d.documento == "11444777000160"  # forma preservada p/ quarentena

    def test_digitos_repetidos_invalido(self):
        d = normalizar_documento("00000000000000", TipoPessoa.PJ)
        assert d is not None and d.valido is False


class TestCpf:
    def test_cpf_valido(self):
        d = normalizar_documento(CPF_VALIDO, TipoPessoa.PF)
        assert d is not None
        assert d.documento == CPF_VALIDO
        assert d.tipo_pessoa == TipoPessoa.PF
        assert d.valido is True
        # Hierarquia matriz/filial nao se aplica a PF
        assert d.raiz is None
        assert d.filial_numero is None
        assert d.is_matriz is None

    def test_cpf_mascarado(self):
        d = normalizar_documento("529.982.247-25", TipoPessoa.PF)
        assert d is not None and d.documento == CPF_VALIDO and d.valido

    def test_cpf_digitos_repetidos_invalido(self):
        d = normalizar_documento("11111111111", TipoPessoa.PF)
        assert d is not None and d.valido is False

    def test_cpf_check_digit_errado(self):
        d = normalizar_documento("52998224724", TipoPessoa.PF)
        assert d is not None and d.valido is False


class TestSemHint:
    def test_11_digitos_cpf_valido_vira_pf(self):
        d = normalizar_documento(CPF_VALIDO)
        assert d is not None and d.tipo_pessoa == TipoPessoa.PF and d.valido

    def test_fallback_para_cnpj_quando_cpf_nao_valida(self):
        """11 digitos que falham como CPF caem no fallback CNPJ (zfill 14)."""
        d = normalizar_documento("12345000165")  # = CNPJ 00012345000165
        assert d is not None
        assert d.tipo_pessoa == TipoPessoa.PJ
        assert d.documento == "00012345000165"
        assert d.valido is True

    def test_ambiguidade_curta_prefere_pf(self):
        """POLITICA: sem hint, string curta que valida nas DUAS formas
        (colisao mod-11 e comum em caudas de poucos digitos — '191' do BB
        e um CPF valido por coincidencia) resolve como PF. Fontes sem hint
        de tipo devem fornece-lo sempre que existir."""
        d = normalizar_documento("191")
        assert d is not None
        assert d.tipo_pessoa == TipoPessoa.PF
        assert d.valido is True

    def test_12_a_14_digitos_so_tenta_cnpj(self):
        d = normalizar_documento(CNPJ_MATRIZ)
        assert d is not None and d.tipo_pessoa == TipoPessoa.PJ and d.valido


class TestEntradaDegenerada:
    def test_none_vazio_e_sem_digitos(self):
        assert normalizar_documento(None) is None
        assert normalizar_documento("") is None
        assert normalizar_documento("n/d") is None

    def test_mais_de_15_digitos_nao_zero_nao_cabe(self):
        assert normalizar_documento("123456789012345678", TipoPessoa.PJ) is None

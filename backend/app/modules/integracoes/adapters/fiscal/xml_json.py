"""Conversao canonica XML -> dict/JSONB dos documentos fiscais.

Regras (determinismo garante re-mapeamento estavel, CLAUDE.md 13.2):
- namespace removido das tags;
- atributo vira chave "@attr";
- tag repetida no mesmo pai vira LISTA (na ordem do documento);
- folha vira o texto (string crua do XML; tipagem e da curadoria, nao do raw);
- subtree `Signature` (assinatura digital XMLDSig) e OMITIDA -- ~1.5KB de
  base64 por documento sem valor analitico; o XML integral permanece no zip
  do bronze para pericia.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET

_NS = re.compile(r"\{.*?\}")

_SKIP_TAGS = {"Signature"}


def strip_ns(tag: str) -> str:
    return _NS.sub("", tag)


def element_to_obj(elem: ET.Element) -> dict | str:
    """Converte um Element em dict canonico (ou string, se folha pura)."""
    out: dict = {}
    for attr, val in elem.attrib.items():
        out[f"@{strip_ns(attr)}"] = val
    children = [c for c in elem if strip_ns(c.tag) not in _SKIP_TAGS]
    if not children:
        text = (elem.text or "").strip()
        if not out:
            return text
        if text:
            out["#text"] = text
        return out
    for child in children:
        tag = strip_ns(child.tag)
        value = element_to_obj(child)
        if tag in out:
            if not isinstance(out[tag], list):
                out[tag] = [out[tag]]
            out[tag].append(value)
        else:
            out[tag] = value
    return out


def xml_to_dict(data: bytes) -> tuple[str, dict]:
    """Parseia o XML e devolve (tag raiz sem namespace, dict canonico)."""
    root = ET.fromstring(data)
    obj = element_to_obj(root)
    if isinstance(obj, str):  # documento degenerado (raiz-folha)
        obj = {"#text": obj}
    return strip_ns(root.tag), obj

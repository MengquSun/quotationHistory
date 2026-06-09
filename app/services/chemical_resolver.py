from __future__ import annotations

import re
from dataclasses import dataclass

CAS_RE = re.compile(r"^\d{2,7}-\d{2}-\d$")

LOCAL_CHEMICALS = {
    "64-17-5": {
        "cas_number": "64-17-5",
        "standard_name": "Ethanol",
        "english_name": "Ethanol",
        "chinese_name": "乙醇",
        "synonyms": ["乙醇", "酒精", "ethanol", "ethyl alcohol", "etoh"],
    },
    "68-12-2": {
        "cas_number": "68-12-2",
        "standard_name": "N,N-Dimethylformamide",
        "english_name": "N,N-Dimethylformamide",
        "chinese_name": "N,N-二甲基甲酰胺",
        "synonyms": ["dmf", "dimethylformamide", "n,n-dimethylformamide", "二甲基甲酰胺"],
    },
}


@dataclass(frozen=True)
class ChemicalCandidate:
    cas_number: str | None
    standard_name: str
    english_name: str | None
    chinese_name: str | None
    synonyms: list[str]
    confidence: float
    source: str


def is_cas_number(value: str) -> bool:
    return bool(CAS_RE.match(value.strip()))


def resolve_local(name: str) -> ChemicalCandidate | None:
    needle = name.strip().lower()
    if not needle:
        return None

    for compound in LOCAL_CHEMICALS.values():
        aliases = [compound["cas_number"], compound["standard_name"], compound.get("english_name", ""), compound.get("chinese_name", "")]
        aliases.extend(compound.get("synonyms", []))
        if needle in {str(alias).lower() for alias in aliases if alias}:
            return ChemicalCandidate(
                cas_number=compound["cas_number"],
                standard_name=compound["standard_name"],
                english_name=compound.get("english_name"),
                chinese_name=compound.get("chinese_name"),
                synonyms=list(compound.get("synonyms", [])),
                confidence=0.98,
                source="local",
            )
    return None


async def resolve_pubchem(name: str) -> ChemicalCandidate | None:
    import httpx

    encoded = name.strip()
    if not encoded:
        return None

    url = f"https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/name/{encoded}/property/IUPACName,Title/JSON"
    try:
        async with httpx.AsyncClient(timeout=8) as client:
            response = await client.get(url)
            response.raise_for_status()
            data = response.json()
    except Exception:
        return None

    props = data.get("PropertyTable", {}).get("Properties", [])
    if not props:
        return None
    first = props[0]
    title = first.get("Title") or first.get("IUPACName") or name
    return ChemicalCandidate(None, title, title, None, [name], 0.72, "pubchem")


async def resolve_chemical(name: str, allow_network: bool = False) -> ChemicalCandidate | None:
    if is_cas_number(name):
        local = resolve_local(name)
        if local:
            return local
        return ChemicalCandidate(name.strip(), name.strip(), None, None, [name.strip()], 0.75, "cas-input")

    local = resolve_local(name)
    if local:
        return local

    if allow_network:
        return await resolve_pubchem(name)
    return None

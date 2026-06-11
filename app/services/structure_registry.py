from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from app import db


class StructureError(ValueError):
    pass


@dataclass(frozen=True)
class StructureProperties:
    canonical_smiles: str | None
    molecular_formula: str | None = None
    molecular_weight: float | None = None
    molfile: str | None = None
    structure_svg: str | None = None
    inchikey: str | None = None


def _clean(value: str | None) -> str | None:
    value = (value or "").strip()
    return value or None


@dataclass
class _SimpleAtom:
    element: str
    x: float = 0
    y: float = 0


@dataclass(frozen=True)
class _SimpleBond:
    left: int
    right: int
    order: int = 1


def _escape_xml(value: str) -> str:
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _parse_smiles_graph(smiles: str) -> tuple[list[_SimpleAtom], list[_SimpleBond]]:
    atoms: list[_SimpleAtom] = []
    bonds: list[_SimpleBond] = []
    branches: list[int] = []
    rings: dict[str, tuple[int, int]] = {}
    current: int | None = None
    bond_order = 1
    i = 0
    organic = {"B", "C", "N", "O", "P", "S", "F", "I"}
    two_char = {"Cl", "Br"}

    while i < len(smiles):
        char = smiles[i]
        if char in "-:/\\":
            bond_order = 1
            i += 1
            continue
        if char == "=":
            bond_order = 2
            i += 1
            continue
        if char == "#":
            bond_order = 3
            i += 1
            continue
        if char == "(":
            if current is not None:
                branches.append(current)
            i += 1
            continue
        if char == ")":
            current = branches.pop() if branches else current
            i += 1
            continue
        if char == ".":
            current = None
            i += 1
            continue
        if char.isdigit() or char == "%":
            if char == "%" and i + 2 < len(smiles):
                ring_id = smiles[i + 1 : i + 3]
                i += 3
            else:
                ring_id = char
                i += 1
            if current is None:
                continue
            if ring_id in rings:
                other, order = rings.pop(ring_id)
                bonds.append(_SimpleBond(other, current, bond_order or order or 1))
            else:
                rings[ring_id] = (current, bond_order)
            bond_order = 1
            continue
        if char == "[":
            end = smiles.find("]", i + 1)
            if end == -1:
                raise StructureError("SMILES 方括号未闭合。")
            token = smiles[i + 1 : end]
            letters = "".join(part for part in token if part.isalpha())
            element = (letters[:2].capitalize() if len(letters) >= 2 and letters[:2].capitalize() in two_char else (letters[:1].upper() or "C"))
            i = end + 1
        elif i + 1 < len(smiles) and smiles[i : i + 2] in two_char:
            element = smiles[i : i + 2]
            i += 2
        elif char in organic or char.lower() == "c":
            element = char.upper()
            i += 1
        else:
            i += 1
            continue

        atoms.append(_SimpleAtom(element=element))
        new_index = len(atoms) - 1
        if current is not None:
            bonds.append(_SimpleBond(current, new_index, bond_order))
        current = new_index
        bond_order = 1

    if not atoms:
        raise StructureError("SMILES 中没有可绘制原子。")
    return atoms, bonds


def render_smiles_svg(smiles: str, width: int = 320, height: int = 220) -> str:
    smiles = _clean(smiles) or ""
    atoms, bonds = _parse_smiles_graph(smiles)
    adjacency: dict[int, list[int]] = {i: [] for i in range(len(atoms))}
    for bond in bonds:
        adjacency[bond.left].append(bond.right)
        adjacency[bond.right].append(bond.left)

    visited: set[int] = set()
    def place(atom_id: int, x: float, y: float, angle: float, depth: int) -> None:
        atoms[atom_id].x = x
        atoms[atom_id].y = y
        visited.add(atom_id)
        children = [n for n in adjacency[atom_id] if n not in visited]
        if not children:
            return
        spread = math.radians(70 if len(children) > 1 else 0)
        start = angle - spread / 2
        step = spread / max(len(children) - 1, 1)
        for idx, child in enumerate(children):
            child_angle = start + step * idx
            place(child, x + math.cos(child_angle), y + math.sin(child_angle), -child_angle, depth + 1)

    for atom_id in range(len(atoms)):
        if atom_id not in visited:
            offset = len([a for a in atoms if a.x or a.y]) * 1.5
            place(atom_id, offset, 0, 0, 0)

    min_x = min(atom.x for atom in atoms)
    max_x = max(atom.x for atom in atoms)
    min_y = min(atom.y for atom in atoms)
    max_y = max(atom.y for atom in atoms)
    span_x = max(max_x - min_x, 1)
    span_y = max(max_y - min_y, 1)
    scale = min((width - 56) / span_x, (height - 56) / span_y, 46)
    pad_x = (width - span_x * scale) / 2
    pad_y = (height - span_y * scale) / 2

    points = [
        (
            pad_x + (atom.x - min_x) * scale,
            pad_y + (atom.y - min_y) * scale,
        )
        for atom in atoms
    ]

    bond_lines: list[str] = []
    for bond in bonds:
        x1, y1 = points[bond.left]
        x2, y2 = points[bond.right]
        dx = x2 - x1
        dy = y2 - y1
        length = math.hypot(dx, dy) or 1
        ox = -dy / length * 3.2
        oy = dx / length * 3.2
        offsets = [(0, 0)] if bond.order == 1 else [(-ox, -oy), (ox, oy)] if bond.order == 2 else [(-ox * 1.5, -oy * 1.5), (0, 0), (ox * 1.5, oy * 1.5)]
        for off_x, off_y in offsets:
            bond_lines.append(
                f'<line x1="{x1 + off_x:.1f}" y1="{y1 + off_y:.1f}" x2="{x2 + off_x:.1f}" y2="{y2 + off_y:.1f}" stroke="#222" stroke-width="2.2" stroke-linecap="round"/>'
            )

    colors = {"N": "#2454ff", "O": "#e11919", "S": "#c79500", "P": "#e58a00", "F": "#2e9b29", "CL": "#1e9c3a", "BR": "#9c2d1f", "I": "#6b4bb8"}
    atom_labels = []
    for idx, atom in enumerate(atoms):
        element = atom.element
        if element == "C" and len(atoms) > 1:
            continue
        x, y = points[idx]
        color = colors.get(element.upper(), "#111")
        atom_labels.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="10" fill="#fff"/>')
        atom_labels.append(
            f'<text x="{x:.1f}" y="{y + 4:.1f}" text-anchor="middle" font-family="Arial, sans-serif" font-size="13" font-weight="700" fill="{color}">{_escape_xml(element)}</text>'
        )

    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-label="chemical structure">
  <rect width="{width}" height="{height}" fill="#fff"/>
  {"".join(bond_lines)}
  {"".join(atom_labels)}
</svg>"""


def derive_structure_properties(smiles: str | None = None, molfile: str | None = None) -> StructureProperties:
    smiles = _clean(smiles)
    molfile = _clean(molfile)
    if not smiles and not molfile:
        raise StructureError("SMILES 或 Molfile 至少填写一个。")

    try:
        from rdkit import Chem
        from rdkit.Chem import AllChem, Descriptors, rdMolDescriptors
        from rdkit.Chem.Draw import rdMolDraw2D
    except ImportError:
        if not smiles:
            raise StructureError("当前环境未安装 RDKit；请填写 SMILES，或安装 RDKit 后再从 Molfile 注册。")
        return StructureProperties(
            canonical_smiles=smiles,
            molfile=molfile,
            structure_svg=render_smiles_svg(smiles),
        )

    mol = Chem.MolFromMolBlock(molfile, removeHs=False, sanitize=True) if molfile else Chem.MolFromSmiles(smiles or "")
    if mol is None:
        raise StructureError("结构无法解析，请检查 SMILES 或 Molfile。")
    Chem.SanitizeMol(mol)
    canonical = Chem.MolToSmiles(mol, canonical=True)
    AllChem.Compute2DCoords(mol)
    drawer = rdMolDraw2D.MolDraw2DSVG(320, 220)
    drawer.DrawMolecule(mol)
    drawer.FinishDrawing()
    inchikey = None
    try:
        inchikey = Chem.MolToInchiKey(mol)
    except Exception:
        inchikey = None
    return StructureProperties(
        canonical_smiles=canonical,
        molecular_formula=rdMolDescriptors.CalcMolFormula(mol),
        molecular_weight=round(Descriptors.MolWt(mol), 4),
        molfile=molfile or Chem.MolToMolBlock(mol),
        structure_svg=drawer.GetDrawingText(),
        inchikey=inchikey,
    )


def register_structure(
    *,
    name: str,
    smiles: str | None = None,
    molfile: str | None = None,
    cas_number: str | None = None,
    notes: str | None = None,
    material_id: int | None = None,
    created_by: str | None = None,
) -> dict[str, Any]:
    db.init_db()
    props = derive_structure_properties(smiles=smiles, molfile=molfile)
    standard_name = name.strip()
    if not standard_name:
        raise StructureError("名称不能为空。")

    if material_id is None:
        material_id = db.find_or_create_material(
            {
                "cas_number": _clean(cas_number),
                "standard_name": standard_name,
                "synonyms": [standard_name],
                "smiles": props.canonical_smiles,
                "inchikey": props.inchikey,
                "match_status": "confirmed",
            },
            standard_name,
        )

    with db.connect() as conn:
        if props.canonical_smiles:
            existing = conn.execute(
                "select * from molecule_structures where canonical_smiles = ? and archived_at is null",
                (props.canonical_smiles,),
            ).fetchone()
            if existing:
                raise StructureError("该化学结构已注册。")
        cur = conn.execute(
            """
            insert into molecule_structures (
                material_id, name, cas_number, canonical_smiles, molfile, molecular_formula,
                molecular_weight, inchikey, structure_svg, notes, created_by, updated_at
            )
            values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, current_timestamp)
            """,
            (
                material_id,
                standard_name,
                _clean(cas_number),
                props.canonical_smiles,
                props.molfile,
                props.molecular_formula,
                props.molecular_weight,
                props.inchikey,
                props.structure_svg,
                _clean(notes),
                created_by,
            ),
        )
        if props.canonical_smiles:
            conn.execute(
                "update materials set smiles = ?, inchikey = ?, updated_at = current_timestamp where id = ?",
                (props.canonical_smiles, props.inchikey, material_id),
            )
        row = conn.execute("select * from molecule_structures where id = ?", (int(cur.lastrowid),)).fetchone()
    return db.row_to_dict(row) or {}


def list_structures(q: str = "", limit: int = 100) -> list[dict[str, Any]]:
    db.init_db()
    like = f"%{q.lower()}%"
    with db.connect() as conn:
        rows = conn.execute(
            """
            select s.*, m.standard_name as material_name
            from molecule_structures s
            left join materials m on m.id = s.material_id
            where s.archived_at is null
              and (
                lower(s.name) like ?
                or lower(coalesce(s.cas_number, '')) like ?
                or lower(coalesce(s.canonical_smiles, '')) like ?
                or lower(coalesce(m.standard_name, '')) like ?
              )
            order by s.updated_at desc, s.id desc
            limit ?
            """,
            (like, like, like, like, min(max(limit, 1), 500)),
        ).fetchall()
    return db.rows_to_dicts(rows)


def get_structure(structure_id: int) -> dict[str, Any] | None:
    db.init_db()
    with db.connect() as conn:
        row = conn.execute("select * from molecule_structures where id = ? and archived_at is null", (structure_id,)).fetchone()
    return db.row_to_dict(row)


def update_structure(
    structure_id: int,
    *,
    name: str | None = None,
    notes: str | None = None,
) -> dict[str, Any]:
    db.init_db()
    with db.connect() as conn:
        row = conn.execute(
            "select * from molecule_structures where id = ? and archived_at is null",
            (structure_id,),
        ).fetchone()
        if not row:
            raise StructureError("结构不存在。")
        conn.execute(
            """
            update molecule_structures
            set name = ?, notes = ?, updated_at = current_timestamp
            where id = ?
            """,
            (_clean(name) or row["name"], _clean(notes), structure_id),
        )
        updated = conn.execute("select * from molecule_structures where id = ?", (structure_id,)).fetchone()
    return db.row_to_dict(updated) or {}


def archive_structure(structure_id: int) -> bool:
    db.init_db()
    with db.connect() as conn:
        row = conn.execute(
            "select id from molecule_structures where id = ? and archived_at is null",
            (structure_id,),
        ).fetchone()
        if not row:
            return False
        conn.execute(
            "update molecule_structures set archived_at = current_timestamp, updated_at = current_timestamp where id = ?",
            (structure_id,),
        )
    return True

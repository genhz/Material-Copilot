from pymatgen.core import Lattice, Structure

from skills.chat import ChatTool
from skills.element_substitution import ElementSubstitutionTool
from skills.material_search import MaterialSearchTool


def test_existing_tool_construction() -> None:
    assert MaterialSearchTool().name == "material_search"
    assert ChatTool().name == "chat"
    assert ElementSubstitutionTool().name == "element_substitution"


def test_element_substitution_uses_compatible_pymatgen_api() -> None:
    structure = Structure(
        lattice=Lattice.cubic(4.0),
        species=["Na", "Cl"],
        coords=[[0, 0, 0], [0.5, 0.5, 0.5]],
    )
    tool = ElementSubstitutionTool()

    modified = tool._apply_substitutions(structure, {"Na": "K"})

    assert tool._generate_formula(modified) == "KCl"

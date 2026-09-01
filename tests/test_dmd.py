from __future__ import annotations

import io
import tarfile
import tempfile
import unittest
import zipfile
from pathlib import Path

from snomed_infectious.dmd import extract_dmd
from snomed_infectious.wide import make_dmd_wide_rows


class DmdExtractionTest(unittest.TestCase):
  def test_selects_classified_product_and_expands_hierarchy(self) -> None:
    with tempfile.TemporaryDirectory() as temporary_directory:
      root = Path(temporary_directory)
      core = root / "dmd.txz"
      bonus = root / "bonus.txz"
      _write_tar(core, {
        "release/f_vmp2_test.xml": _xml("VIRTUAL_MED_PRODUCTS", "<VMPS>"
          "<VMP><VPID>v1</VPID><VTMID>t1</VTMID><NM>Amoxicillin 500mg capsule</NM></VMP>"
          "<VMP><VPID>v2</VPID><VTMID>t2</VTMID><NM>Atenolol 50mg tablet</NM></VMP></VMPS>"),
        "release/f_amp2_test.xml": _xml("ACTUAL_MEDICINAL_PRODUCTS", "<AMPS>"
          "<AMP><APID>a1</APID><VPID>v1</VPID><NM>Amoxicillin brand</NM><DESC>Amoxicillin brand (Supplier)</DESC></AMP>"
          "<AMP><APID>a2</APID><VPID>v2</VPID><NM>Atenolol brand</NM><DESC>Atenolol brand (Supplier)</DESC></AMP></AMPS>"),
        "release/f_vtm2_test.xml": _xml("VIRTUAL_THERAPEUTIC_MOIETIES", ""
          "<VTM><VTMID>t1</VTMID><NM>Amoxicillin</NM></VTM>"
          "<VTM><VTMID>t2</VTMID><NM>Atenolol</NM></VTM>"),
        "release/f_vmpp2_test.xml": _xml("VIRTUAL_MED_PRODUCT_PACK", "<VMPPS>"
          "<VMPP><VPPID>p1</VPPID><NM>Amoxicillin pack</NM><VPID>v1</VPID></VMPP></VMPPS>"),
        "release/f_ampp2_test.xml": _xml("ACTUAL_MEDICINAL_PROD_PACKS", "<AMPPS>"
          "<AMPP><APPID>q1</APPID><NM>Amoxicillin actual pack</NM><VPPID>p1</VPPID><APID>a1</APID></AMPP>"
          "</AMPPS>"),
        "release/f_ingredient2_test.xml": _xml("INGREDIENT_SUBSTANCES", ""
          "<ING><ISID>i1</ISID><NM>Amoxicillin</NM></ING>"),
      })
      bnf_zip = _zip_bytes({
        "f_bnf1_test.xml": _xml("BNF_DETAILS", "<VMPS>"
          "<VMP><VPID>v1</VPID><BNF>05010103</BNF><ATC>J01CA04</ATC></VMP>"
          "<VMP><VPID>v2</VPID><BNF>02040000</BNF><ATC>C07AB03</ATC></VMP></VMPS><AMPS/>")
      })
      _write_tar(bonus, {
        "release/week-BNF.zip": bnf_zip,
        "release/VTM_INGREDIENTS/f_vtm_ing1_test.xml": _xml(
          "VTM_INGREDIENTS", "<VTM_ING><VTMID>t1</VTMID><ISID>i1</ISID></VTM_ING>"
        ),
      })

      result = extract_dmd(core, bonus, ("05",), ("J01",))

      self.assertEqual(result.selected_vmp_ids, {"v1"})
      self.assertEqual(result.selected_amp_ids, {"a1"})
      self.assertIn("Amoxicillin actual pack", {row["term"] for row in result.term_rows})
      self.assertNotIn("Atenolol 50mg tablet", {row["term"] for row in result.term_rows})
      self.assertIn(
        ("t1", "i1"),
        {(row["source_id"], row["target_id"]) for row in result.relationship_rows},
      )
      wide_rows = make_dmd_wide_rows(result, core)
      pack_row = next(row for row in wide_rows if row["concept_id"] == "q1")
      self.assertEqual(pack_row["generic_products"], ["Amoxicillin 500mg capsule"])
      self.assertEqual(pack_row["ingredients"], ["Amoxicillin"])
      self.assertEqual(pack_row["bnf_codes"], ["05010103"])


def _xml(root: str, body: str) -> bytes:
  return f'<?xml version="1.0" encoding="utf-8"?><{root}>{body}</{root}>'.encode()


def _zip_bytes(members: dict[str, bytes]) -> bytes:
  output = io.BytesIO()
  with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
    for name, data in members.items():
      archive.writestr(name, data)
  return output.getvalue()


def _write_tar(path: Path, members: dict[str, bytes]) -> None:
  with tarfile.open(path, "w:xz") as archive:
    for name, data in members.items():
      info = tarfile.TarInfo(name)
      info.size = len(data)
      archive.addfile(info, io.BytesIO(data))


if __name__ == "__main__":
  unittest.main()

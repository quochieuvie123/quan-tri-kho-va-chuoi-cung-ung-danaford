from django.test import TestCase
from .models import NhaCungCap


class NhaCungCapModelTests(TestCase):
    def test_str_returns_supplier_name(self):
        supplier = NhaCungCap(
            ma_ncc="NCC-TEST",
            ten_ncc="Nha cung cap thu nghiem",
            dia_chi_ncc="Da Nang",
            mst="MST-TEST",
        )
        self.assertEqual(str(supplier), "Nha cung cap thu nghiem")

"""Kiểm thử phần tính toán thuần (không cần database): python -m unittest analytics.tests"""
import unittest

from . import forecast as f


class DuBaoTest(unittest.TestCase):
    def test_cong_thang(self):
        self.assertEqual(f.cong_thang(2026, 11, 2), (2027, 1))
        self.assertEqual(f.cong_thang(2026, 1, -1), (2025, 12))

    def test_dien_khuyet_bang_trung_binh_truot(self):
        self.assertEqual(f.dien_khuyet([5, 0, 0, 7, 0], {1, 2, 4}), [5, 5, 5, 7, 6])

    def test_mua_vu_dinh_thang_2(self):
        # 36 tháng, kết thúc 11/2026, đỉnh vào tháng 2 và 3 hằng năm
        chuoi = []
        for i in range(36):
            _, thang = f.cong_thang(2026, 11, i - 35)
            chuoi.append(10 + 0.2 * i + (6 if thang in (2, 3) else 0))
        thuong, _, _ = f.du_bao_sarima(chuoi, 2026, 11, 1)   # 12/2026
        dinh, pp, cb = f.du_bao_sarima(chuoi, 2026, 11, 3)   # 02/2027
        self.assertGreater(dinh, thuong + 4)
        self.assertEqual(cb, [])
        self.assertIn("SARIMA", pp)

    def test_thieu_du_lieu_co_canh_bao(self):
        v, pp, cb = f.du_bao_sarima([3, 5], 2026, 11, 1)
        self.assertEqual(v, 4)
        self.assertTrue(cb)

    def test_poq(self):
        self.assertEqual(f.tinh_poq(4.2, 10, 2, 1, 1.5), 0)           # tồn đủ
        self.assertEqual(f.tinh_poq(20, 3, 0, 0, 2, chi_tieu=8), 8)   # bị chặn bởi chỉ tiêu
        self.assertEqual(f.tinh_poq(5.4, 1, 2, 1, 1), 6)              # 5.4+2+1-1-1 = 6.4 -> làm tròn 6


if __name__ == "__main__":
    unittest.main()

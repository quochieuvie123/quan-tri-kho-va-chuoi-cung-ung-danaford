from datetime import date
from types import SimpleNamespace
from unittest.mock import Mock
from django.test import SimpleTestCase
from django.template.loader import render_to_string
from .views import criteria_for, contract_summary, find_suitable


class ContractPresentationTests(SimpleTestCase):
    def contract(self, state='CHO_XU_LY'):
        cars = [SimpleNamespace(ten_xe='Ranger XLS', phien_ban='', mau_sac=color) for color in ('Trắng', 'Đen')]
        lines = Mock()
        lines.all.return_value = [SimpleNamespace(xe=car) for car in cars]
        requirements = Mock()
        requirements.all.return_value = []
        return SimpleNamespace(yeu_cau_xe=requirements, chi_nhanh=SimpleNamespace(pk='CN01', ten_cn='Đà Nẵng'), pk='HD01', dong_xe_yeu_cau='', phien_ban_yeu_cau='', mau_sac_yeu_cau='',
            chitiethopdong_set=lines, trang_thai=state, get_trang_thai_display=lambda: 'Hoàn tất',
            khach_hang_id='KH01', khach_hang=SimpleNamespace(ten_kh='Khách hàng'), chi_nhanh_id='CN01',
            ngay_ky=None, so_tien_coc=0, ngay_du_kien_giao=None)

    def test_multiple_legacy_requirements_are_visible_without_inventing_version(self):
        hd = self.contract()
        criteria, warning = criteria_for(hd)
        self.assertEqual(len(criteria), 2)
        self.assertTrue(warning)
        html = render_to_string('contracts/detail.html', {'hop_dong': {
            'ma_hd': hd.pk, 'tieu_chi_xe': criteria, 'canh_bao': warning}})
        self.assertIn('Ranger XLS', html)
        self.assertIn('Trắng', html)
        self.assertIn('Đen', html)
        self.assertIn('Chưa có phiên bản', html)

    def test_completed_contract_cannot_suggest_cars(self):
        hd = self.contract('HOAN_TAT')
        user = Mock(is_authenticated=True, is_active=True, is_superuser=True)
        summary = contract_summary(hd, user)
        self.assertEqual(summary['trang_thai_hien_thi'], 'Hoàn tất')
        self.assertFalse(summary['thao_tac']['de_xuat_xe'])
        self.assertEqual(find_suitable(hd)[1], [])
        self.assertIn('hoàn tất', find_suitable(hd)[2])

    def test_detail_template_contains_delivery_date_input(self):
        html = render_to_string('contracts/detail.html', {'hop_dong': {
            'ma_hd': 'HD99', 'tieu_chi_xe': [], 'canh_bao': None, 'ngay_du_kien_giao': None
        }, 'co_the_chinh_sua': True})
        self.assertIn('name="ngay_du_kien_giao"', html)
        self.assertIn('Lưu ngày giao', html)
        self.assertIn('openDateModal', html)

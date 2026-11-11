"""Nhu cầu còn chờ giao, độc lập với việc đã chọn VIN hay chưa."""
from database.models import HopDong, TrangThaiHopDong, TrangThaiPhieuXuat


def matches(car, requirement):
    return all((actual or '').strip().casefold() == (expected or '').strip().casefold()
               for actual, expected in ((car.ten_xe, requirement['dong_xe']),
               (car.phien_ban, requirement['phien_ban']), (car.mau_sac, requirement['mau_sac'])))


def remaining_requirements(contract, include_reserved=False):
    if contract.trang_thai == TrangThaiHopDong.HOAN_TAT:
        return []
    states = [TrangThaiPhieuXuat.DA_DUYET]
    if include_reserved:
        states.append(TrangThaiPhieuXuat.CHO_DUYET)
    result = []
    for line in contract.chitiethopdong_set.exclude(phieuxuatkho__trang_thai__in=states).select_related('xe'):
        car = line.xe
        result.append({'dong_xe': car.ten_xe, 'phien_ban': getattr(car, 'phien_ban', '') or '',
                       'mau_sac': car.mau_sac or '', 'so_luong': 1})
    return result


def pending_demand():
    for contract in HopDong.objects.exclude(trang_thai=TrangThaiHopDong.HOAN_TAT).prefetch_related('chitiethopdong_set__xe'):
        for row in remaining_requirements(contract):
            yield dict(row, ma_hd=contract.pk)

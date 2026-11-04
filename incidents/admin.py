from django.contrib import admin

from .models import AnhSuCo, DvvcLienHe, HoSoSuCo, LichSuPhanHoi

admin.site.register([DvvcLienHe, HoSoSuCo, AnhSuCo, LichSuPhanHoi])

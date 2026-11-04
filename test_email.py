import os

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django
django.setup()

from django.conf import settings
from django.core.mail import send_mail

# Kiểm tra email gửi
print("Email gửi:", os.environ.get("EMAIL_HOST_USER", ""))

# Gửi email thử
result = send_mail(
    subject="Kiểm tra gửi email Django",
    message="Đây là email kiểm tra từ hệ thống DanaFord.",
    from_email=settings.DEFAULT_FROM_EMAIL,
    recipient_list=["fordvn@gmail.com"],
    fail_silently=False
)

print("Số email gửi thành công:", result)
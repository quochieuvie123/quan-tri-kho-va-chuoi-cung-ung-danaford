from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import TemplateView


class PlaceholderView(LoginRequiredMixin, TemplateView):
    template_name = "core/placeholder.html"
    title = ""

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["page_title"] = self.title
        return ctx


from django.shortcuts import render

# Create your views here.
from django.conf import settings
from django.core.mail import send_mail

send_mail(
    subject="Lệnh lưu chuyển xe",
    message="Nội dung lệnh lưu chuyển",
    from_email=settings.DEFAULT_FROM_EMAIL,
    recipient_list=settings.TRANSFER_RECEIVER_EMAILS,
    fail_silently=False,
)
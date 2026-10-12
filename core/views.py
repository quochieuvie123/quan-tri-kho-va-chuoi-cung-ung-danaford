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

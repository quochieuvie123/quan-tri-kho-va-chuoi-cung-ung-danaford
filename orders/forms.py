from django import forms

class AllocationUploadForm(forms.Form):
    file = forms.FileField(
        label="Chọn file Excel"
    )
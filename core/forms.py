from django import forms
from django.db import models
from core.models import Crop, Field, FieldCrop, Operation, OperationType, Season
from django.contrib.auth import get_user_model

User = get_user_model()


class OperationForm(forms.ModelForm):

    class Meta:
        model = Operation
        fields = ["type", "date", "status", "performed_by", "description"]
        widgets = {
            "date": forms.DateInput(attrs={"type": "date", "class": "form-control"}),
            "status": forms.Select(attrs={"class": "form-select"}),
            "performed_by": forms.Select(attrs={"class": "form-select"}),
            "description": forms.Textarea(attrs={
                "class": "form-control",
                "rows": 2,
                "placeholder": "Add optional notes..."
                
            }),
            "type": forms.Select(attrs={"class": "form-select"}),
        }

    def __init__(self, *args, **kwargs):
        user = kwargs.pop("user", None)
        self.schedule_mode = kwargs.pop("schedule_mode", False)
        super().__init__(*args, **kwargs)

        if self.schedule_mode:
            self.fields["date"].required = False

        if user:
            owner_filter = None
            if user.role == "agronomist":
                from core.models import AgronomistAssignment
                owner_ids = AgronomistAssignment.objects.filter(agronomist=user).values_list("owner_id", flat=True)
                self.fields["performed_by"].queryset = User.objects.filter(role="worker", owner_id__in=owner_ids)
                owner_filter = {"owner_id__in": owner_ids}
            else:
                self.fields["performed_by"].queryset = User.objects.filter(role="worker", owner=user)
                owner_filter = {"owner": user}

            self.fields["type"].queryset = OperationType.objects.filter(
                models.Q(owner__isnull=True) | models.Q(**owner_filter)
            ).distinct()

class WorkerRegistrationForm(forms.ModelForm):
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={"class": "form-control"})
    )

    email = forms.EmailField(
        required=True,
        widget=forms.EmailInput(attrs={"class": "form-control"}),
        error_messages={
            "required": "Email is required"
        }
    )

    class Meta:
        model = User
        fields = ["username", "email", "password"]
        widgets = {
            "username": forms.TextInput(attrs={"class": "form-control"}),
        }
    
    def __init__(self, *args, **kwargs):
        self.owner = kwargs.pop("owner", None)
        super().__init__(*args, **kwargs)

    def clean_email(self):
        email = self.cleaned_data["email"]
        if User.objects.filter(email=email).exists():
            raise forms.ValidationError("This email is already taken.")
        return email

    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data["password"])
        user.role = "worker"
        user.owner = self.owner
        if commit:
            user.save()
        return user

class InviteAgronomistForm(forms.Form):
    email = forms.EmailField(
        label="Agronomist Email",
        widget=forms.EmailInput(attrs={"class": "form-control"}),
    )


class SeasonCreateForm(forms.ModelForm):
    class Meta:
        from core.models import Season
        model = Season
        fields = ["name", "start_date", "end_date"]   # year is auto-derived
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control"}),
            "start_date": forms.DateInput(attrs={"type": "date", "class": "form-control"}),
            "end_date":   forms.DateInput(attrs={"type": "date", "class": "form-control"}),
        }

    def clean(self):
        cd = super().clean()
        s, e = cd.get("start_date"), cd.get("end_date")
        if s and e and e <= s:
            raise forms.ValidationError("End date must be after start date.")
        return cd


class FieldCropCreateForm(forms.ModelForm):
    class Meta:
        model = FieldCrop
        fields = ["field", "season", "crop", "planting_date", "harvest_date"]
        widgets = {
            "field": forms.Select(attrs={"class": "form-select"}),
            "season": forms.Select(attrs={"class": "form-select"}),
            "crop": forms.Select(attrs={"class": "form-select"}),
            "planting_date": forms.DateInput(attrs={"type": "date", "class": "form-control"}),
            "harvest_date": forms.DateInput(attrs={"type": "date", "class": "form-control"}),
        }

    def __init__(self, *args, **kwargs):
        user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)

        self.fields["harvest_date"].required = False

        if user and user.role == "owner":
            self.fields["field"].queryset = Field.objects.filter(owner=user).order_by("name")
            self.fields["season"].queryset = Season.objects.filter(owner=user).order_by("-year", "name")
        else:
            self.fields["field"].queryset = Field.objects.all().order_by("name")
            self.fields["season"].queryset = Season.objects.all().order_by("-year", "name")

        self.fields["crop"].queryset = Crop.objects.all().order_by("name")

    def clean(self):
        cleaned_data = super().clean()
        field = cleaned_data.get("field")
        crop = cleaned_data.get("crop")
        season = cleaned_data.get("season")

        if field and crop and season:
            duplicate_qs = FieldCrop.objects.filter(field=field, crop=crop, season=season)
            if self.instance.pk:
                duplicate_qs = duplicate_qs.exclude(pk=self.instance.pk)
            if duplicate_qs.exists():
                raise forms.ValidationError("This crop is already assigned to the selected field and season.")

            if season.owner_id and field.owner_id != season.owner_id:
                self.add_error("season", "Selected season does not belong to this field owner.")

        return cleaned_data

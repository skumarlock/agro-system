from django import forms
from django.db import models
from core.models import (
    Crop,
    Device,
    DeviceData,
    Field,
    FieldCrop,
    Operation,
    OperationType,
    Purchase,
    Recommendation,
    Resource,
    Season,
    Stock,
    Supplier,
)
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

class OwnerRegistrationForm(forms.ModelForm):
    """Public self-registration form. Creates a user with role=owner."""

    password1 = forms.CharField(
        label="Пароль",
        widget=forms.PasswordInput(attrs={"class": "form-control", "placeholder": "Минимум 8 символов"}),
    )
    password2 = forms.CharField(
        label="Подтвердите пароль",
        widget=forms.PasswordInput(attrs={"class": "form-control", "placeholder": "Повторите пароль"}),
    )

    class Meta:
        model = User
        fields = ["username", "email", "first_name", "last_name"]
        labels = {
            "username": "Имя пользователя",
            "email": "Email",
            "first_name": "Имя",
            "last_name": "Фамилия",
        }
        widgets = {
            "username": forms.TextInput(attrs={"class": "form-control", "placeholder": "Латинские буквы и цифры"}),
            "email": forms.EmailInput(attrs={"class": "form-control", "placeholder": "example@mail.com"}),
            "first_name": forms.TextInput(attrs={"class": "form-control"}),
            "last_name": forms.TextInput(attrs={"class": "form-control"}),
        }

    def clean_email(self):
        email = self.cleaned_data.get("email")
        if email and User.objects.filter(email=email).exists():
            raise forms.ValidationError("Этот email уже зарегистрирован.")
        return email

    def clean_username(self):
        username = self.cleaned_data.get("username")
        if username and User.objects.filter(username=username).exists():
            raise forms.ValidationError("Это имя пользователя уже занято.")
        return username

    def clean(self):
        cleaned_data = super().clean()
        p1 = cleaned_data.get("password1")
        p2 = cleaned_data.get("password2")
        if p1 and p2 and p1 != p2:
            self.add_error("password2", "Пароли не совпадают.")
        if p1 and len(p1) < 8:
            self.add_error("password1", "Пароль должен содержать минимум 8 символов.")
        return cleaned_data

    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data["password1"])
        user.role = "owner"
        user.owner = None
        if commit:
            user.save()
        return user


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


class PurchaseForm(forms.ModelForm):
    supplier_choice = forms.ModelChoiceField(
        queryset=Supplier.objects.none(),
        required=False,
        label="Поставщик",
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    supplier_new = forms.CharField(
        required=False,
        label="Новый поставщик",
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "Если поставщика нет в списке"}),
    )

    class Meta:
        model = Purchase
        fields = ["resource", "quantity", "price_per_unit"]
        labels = {
            "resource": "Ресурс",
            "quantity": "Количество",
            "price_per_unit": "Цена за единицу",
        }
        widgets = {
            "resource": forms.Select(attrs={"class": "form-select"}),
            "quantity": forms.NumberInput(attrs={"class": "form-control", "step": "0.01", "min": "0.01"}),
            "price_per_unit": forms.NumberInput(attrs={"class": "form-control", "step": "0.01", "min": "0", "placeholder": "Можно оставить пустым"}),
        }

    def __init__(self, *args, **kwargs):
        owner = kwargs.pop("owner", None)
        super().__init__(*args, **kwargs)
        self.fields["resource"].queryset = Resource.objects.order_by("name")
        self.fields["price_per_unit"].required = False
        if owner:
            self.fields["supplier_choice"].queryset = Supplier.objects.filter(owner=owner)


class StockAdjustForm(forms.Form):
    resource = forms.ModelChoiceField(
        label="Ресурс",
        queryset=Resource.objects.order_by("name"),
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    quantity_current = forms.DecimalField(
        label="Текущее количество",
        min_value=0,
        widget=forms.NumberInput(attrs={"class": "form-control", "step": "0.01", "min": "0"}),
    )


class RecommendationForm(forms.Form):
    owner = forms.ModelChoiceField(
        queryset=User.objects.none(),
        required=False,
        label="Владелец",
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    target = forms.ChoiceField(
        label="Объект",
        choices=[],
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    text = forms.CharField(
        label="Рекомендация",
        widget=forms.Textarea(attrs={"class": "form-control", "rows": 3}),
    )

    def __init__(self, *args, **kwargs):
        user = kwargs.pop("user", None)
        owner = kwargs.pop("owner", None)
        super().__init__(*args, **kwargs)
        if user and user.role == "agronomist":
            from core.models import AgronomistAssignment

            self.fields["owner"].queryset = User.objects.filter(
                id__in=AgronomistAssignment.objects.filter(agronomist=user).values_list("owner_id", flat=True)
            )
            self.fields["owner"].required = True
            if owner:
                self.fields["owner"].initial = owner.pk
        else:
            self.fields.pop("owner")

        if owner:
            choices = []
            choices += [(f"field:{f.pk}", f"Поле: {f.name}") for f in Field.objects.filter(owner=owner).order_by("name")]
            choices += [
                (f"operation:{op.pk}", f"Операция: {op.type.name} / {op.field_crop.field.name} / {op.date}")
                for op in Operation.objects.filter(field_crop__field__owner=owner).select_related("type", "field_crop__field").order_by("-date")[:80]
            ]
            choices += [
                (f"crop:{fc.pk}", f"Культура: {fc.crop.name} / {fc.field.name} / {fc.season}")
                for fc in FieldCrop.objects.filter(field__owner=owner).select_related("crop", "field", "season").order_by("-season__year")[:80]
            ]
            self.fields["target"].choices = choices


class DeviceForm(forms.ModelForm):
    TYPE_CHOICES = [
        ("soil_moisture", "Влажность почвы"),
        ("temperature", "Температура"),
        ("rain", "Датчик осадков"),
        ("water_flow", "Расход воды"),
        ("custom", "Свой тип"),
    ]
    STATUS_CHOICES = [
        ("active", "Активен"),
        ("manual", "Ручной ввод"),
        ("maintenance", "На обслуживании"),
        ("offline", "Отключен"),
    ]

    type_preset = forms.ChoiceField(label="Тип", choices=TYPE_CHOICES, widget=forms.Select(attrs={"class": "form-select"}))
    type_custom = forms.CharField(required=False, label="Свой тип", widget=forms.TextInput(attrs={"class": "form-control"}))

    class Meta:
        model = Device
        fields = ["field", "status"]
        labels = {
            "field": "Поле",
            "status": "Статус",
        }
        widgets = {
            "field": forms.Select(attrs={"class": "form-select"}),
            "status": forms.Select(choices=[
                ("active", "Активен"),
                ("manual", "Ручной ввод"),
                ("maintenance", "На обслуживании"),
                ("offline", "Отключен"),
            ], attrs={"class": "form-select"}),
        }

    def __init__(self, *args, **kwargs):
        owner = kwargs.pop("owner", None)
        super().__init__(*args, **kwargs)
        if owner:
            self.fields["field"].queryset = Field.objects.filter(owner=owner).order_by("name")

    def save(self, commit=True):
        device = super().save(commit=False)
        preset = self.cleaned_data.get("type_preset")
        device.type = self.cleaned_data.get("type_custom") if preset == "custom" else dict(self.TYPE_CHOICES).get(preset, preset)
        if commit:
            device.save()
        return device

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("type_preset") == "custom" and not (cleaned.get("type_custom") or "").strip():
            self.add_error("type_custom", "Укажите свой тип устройства.")
        return cleaned


class DeviceForm(forms.ModelForm):
    TYPE_CHOICES = [
        ("soil_moisture", "Влажность почвы"),
        ("temperature", "Температура"),
        ("rain", "Датчик осадков"),
        ("water_flow", "Расход воды"),
        ("custom", "Свой тип"),
    ]
    STATUS_CHOICES = [
        ("active", "Активен"),
        ("manual", "Ручной ввод"),
        ("maintenance", "На обслуживании"),
        ("offline", "Отключен"),
    ]

    type_preset = forms.ChoiceField(label="Тип", choices=TYPE_CHOICES, widget=forms.Select(attrs={"class": "form-select"}))
    type_custom = forms.CharField(required=False, label="Свой тип", widget=forms.TextInput(attrs={"class": "form-control"}))

    class Meta:
        model = Device
        fields = ["field", "status"]
        labels = {
            "field": "Поле",
            "status": "Статус",
        }
        widgets = {
            "field": forms.Select(attrs={"class": "form-select"}),
            "status": forms.Select(choices=[
                ("active", "Активен"),
                ("manual", "Ручной ввод"),
                ("maintenance", "На обслуживании"),
                ("offline", "Отключен"),
            ], attrs={"class": "form-select"}),
        }

    def __init__(self, *args, **kwargs):
        owner = kwargs.pop("owner", None)
        super().__init__(*args, **kwargs)
        if owner:
            self.fields["field"].queryset = Field.objects.filter(owner=owner).order_by("name")

    def save(self, commit=True):
        device = super().save(commit=False)
        preset = self.cleaned_data.get("type_preset")
        device.type = self.cleaned_data.get("type_custom") if preset == "custom" else dict(self.TYPE_CHOICES).get(preset, preset)
        if commit:
            device.save()
        return device

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("type_preset") == "custom" and not (cleaned.get("type_custom") or "").strip():
            self.add_error("type_custom", "Укажите свой тип датчика.")
        return cleaned


class DeviceDataForm(forms.ModelForm):
    class Meta:
        model = DeviceData
        fields = ["value"]
        widgets = {
            "value": forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
        }

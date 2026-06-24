from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.utils.text import slugify
from .models import (
    Organization, Venue, Piano, WorkOrder, ConditionReading, ConditionLevel,
    MaintenanceSchedule, ScheduleTemplate, Part, Technician, CompanySettings,
    Company, CompanyInvitation, CompanyMembership, IntervalUnit,
)
from .tenancy import company_users


class SignUpForm(UserCreationForm):
    first_name = forms.CharField(max_length=150)
    last_name = forms.CharField(max_length=150)
    email = forms.EmailField()

    class Meta:
        model = Technician
        fields = ['username', 'first_name', 'last_name', 'email', 'password1', 'password2']

    def save(self, commit=True):
        user = super().save(commit=False)
        user.is_active = False
        user.role_admin = False
        user.role_technician = False
        if commit:
            user.save()
        return user


class TechnicianCreateForm(UserCreationForm):
    first_name = forms.CharField(max_length=150)
    last_name = forms.CharField(max_length=150)
    email = forms.EmailField(required=False)
    role_admin = forms.BooleanField(required=False)
    role_technician = forms.BooleanField(required=False, initial=True)

    class Meta:
        model = Technician
        fields = [
            'username', 'first_name', 'last_name', 'email', 'is_active',
            'password1', 'password2',
        ]


class TechnicianUpdateForm(forms.ModelForm):
    first_name = forms.CharField(max_length=150)
    last_name = forms.CharField(max_length=150)
    email = forms.EmailField(required=False)
    role_admin = forms.BooleanField(required=False)
    role_technician = forms.BooleanField(required=False)

    class Meta:
        model = Technician
        fields = [
            'username', 'first_name', 'last_name', 'email', 'is_active',
        ]


class OrganizationForm(forms.ModelForm):
    def __init__(self, *args, company=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.company = company

    class Meta:
        model = Organization
        fields = [
            'name', 'short_name', 'address',
            'contact_name', 'contact_email', 'contact_phone',
            'notes',
        ]


class VenueForm(forms.ModelForm):
    def __init__(self, *args, company=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.company = company
        if company:
            self.fields['organization'].queryset = Organization.objects.filter(company=company)

    class Meta:
        model = Venue
        fields = [
            'name', 'short_name', 'organization', 'address',
            'on_site_contact', 'parking_notes', 'access_notes',
            'notes',
        ]


class PianoForm(forms.ModelForm):
    def __init__(self, *args, company=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.company = company
        if company:
            self.fields['venue'].queryset = Venue.objects.filter(company=company)

    class Meta:
        model = Piano
        fields = [
            'name', 'make', 'model', 'serial_number',
            'piano_type', 'venue',
            'section', 'room', 'room_description', 'room_access_notes',
            'year_built', 'year_acquired',
            'tuning_interval_value', 'tuning_interval_unit',
            'regulation_interval_value', 'regulation_interval_unit',
            'voicing_interval_value', 'voicing_interval_unit',
            'cleaning_interval_value', 'cleaning_interval_unit',
            'notes',
        ]


class BulkPianoIntervalForm(forms.Form):
    piano_ids = forms.MultipleChoiceField(widget=forms.CheckboxSelectMultiple)

    update_tuning = forms.BooleanField(required=False)
    tuning_interval_value = forms.IntegerField(min_value=1, required=False)
    tuning_interval_unit = forms.ChoiceField(
        choices=IntervalUnit.choices,
        required=False,
    )

    update_regulation = forms.BooleanField(required=False)
    regulation_interval_value = forms.IntegerField(min_value=1, required=False)
    regulation_interval_unit = forms.ChoiceField(
        choices=IntervalUnit.choices,
        required=False,
    )

    update_voicing = forms.BooleanField(required=False)
    voicing_interval_value = forms.IntegerField(min_value=1, required=False)
    voicing_interval_unit = forms.ChoiceField(
        choices=IntervalUnit.choices,
        required=False,
    )

    update_cleaning = forms.BooleanField(required=False)
    cleaning_interval_value = forms.IntegerField(min_value=1, required=False)
    cleaning_interval_unit = forms.ChoiceField(
        choices=IntervalUnit.choices,
        required=False,
    )

    interval_tasks = (
        'tuning',
        'regulation',
        'voicing',
        'cleaning',
    )

    def __init__(self, *args, pianos=None, **kwargs):
        super().__init__(*args, **kwargs)
        pianos = list(pianos or [])
        self.fields['piano_ids'].choices = [
            (piano.pk, piano.name) for piano in pianos
        ]

    def clean(self):
        cleaned = super().clean()
        selected_tasks = [
            task for task in self.interval_tasks
            if cleaned.get(f'update_{task}')
        ]
        if not cleaned.get('piano_ids'):
            raise forms.ValidationError('Select at least one piano to update.')
        if not selected_tasks:
            raise forms.ValidationError('Choose at least one interval to update.')
        for task in selected_tasks:
            if not cleaned.get(f'{task}_interval_value'):
                self.add_error(
                    f'{task}_interval_value',
                    'Enter an interval value.',
                )
            if not cleaned.get(f'{task}_interval_unit'):
                self.add_error(
                    f'{task}_interval_unit',
                    'Choose an interval unit.',
                )
        return cleaned

    def interval_updates(self):
        updates = {}
        for task in self.interval_tasks:
            if self.cleaned_data.get(f'update_{task}'):
                updates[f'{task}_interval_value'] = self.cleaned_data[f'{task}_interval_value']
                updates[f'{task}_interval_unit'] = self.cleaned_data[f'{task}_interval_unit']
        return updates


class WorkOrderForm(forms.ModelForm):
    def __init__(self, *args, company=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.company = company
        if company:
            self.fields['piano'].queryset = Piano.objects.filter(company=company, is_active=True).select_related('venue')
            self.fields['assigned_tech'].queryset = company_users(company, technicians_only=True)

    class Meta:
        model = WorkOrder
        fields = [
            'piano', 'order_type', 'task_type', 'priority',
            'assigned_tech', 'is_team_job', 'description', 'due_date',
        ]
        widgets = {
            'due_date': forms.DateInput(attrs={'type': 'date'}),
        }


class WorkOrderCompleteForm(forms.Form):
    """Form for the work-order completion flow."""
    hours_worked = forms.DecimalField(
        max_digits=5, decimal_places=2, min_value=0,
        widget=forms.NumberInput(attrs={'step': '0.25', 'placeholder': '0.00'}),
    )
    work_performed = forms.CharField(
        widget=forms.Textarea(attrs={'rows': 3, 'placeholder': 'Describe the work performed…'}),
    )
    notes = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={'rows': 2, 'placeholder': 'Additional notes (optional)'}),
    )
    include_condition = forms.BooleanField(
        required=False,
        label='Add condition reading',
    )

    # Condition reading fields (only validated when include_condition is checked)
    overall_rating = forms.ChoiceField(
        required=False,
        choices=[('', '— Select —')] + list(ConditionLevel.choices),
    )
    regulation_condition = forms.ChoiceField(required=False, choices=[('', '—')] + list(ConditionLevel.choices))
    voicing_condition = forms.ChoiceField(required=False, choices=[('', '—')] + list(ConditionLevel.choices))
    belly_condition = forms.ChoiceField(required=False, choices=[('', '—')] + list(ConditionLevel.choices))
    soundboard_condition = forms.ChoiceField(required=False, choices=[('', '—')] + list(ConditionLevel.choices))
    pinblock_condition = forms.ChoiceField(required=False, choices=[('', '—')] + list(ConditionLevel.choices))
    strings_condition = forms.ChoiceField(required=False, choices=[('', '—')] + list(ConditionLevel.choices))
    hammers_condition = forms.ChoiceField(required=False, choices=[('', '—')] + list(ConditionLevel.choices))
    keys_condition = forms.ChoiceField(required=False, choices=[('', '—')] + list(ConditionLevel.choices))
    pedals_condition = forms.ChoiceField(required=False, choices=[('', '—')] + list(ConditionLevel.choices))
    case_condition = forms.ChoiceField(required=False, choices=[('', '—')] + list(ConditionLevel.choices))
    pitch_before_cents = forms.DecimalField(required=False, max_digits=6, decimal_places=2)
    pitch_after_cents = forms.DecimalField(required=False, max_digits=6, decimal_places=2)
    humidity_pct = forms.DecimalField(required=False, max_digits=5, decimal_places=2)
    temperature_f = forms.DecimalField(required=False, max_digits=5, decimal_places=2)
    condition_notes = forms.CharField(required=False, widget=forms.Textarea(attrs={'rows': 3}))


class ConditionReadingForm(forms.ModelForm):
    class Meta:
        model = ConditionReading
        fields = [
            'overall_rating',
            'regulation_condition', 'voicing_condition',
            'belly_condition', 'soundboard_condition',
            'pinblock_condition', 'strings_condition',
            'hammers_condition', 'keys_condition',
            'pedals_condition', 'case_condition',
            'pitch_before_cents', 'pitch_after_cents',
            'humidity_pct', 'temperature_f',
            'notes',
        ]


class ScheduleTemplateForm(forms.ModelForm):
    class Meta:
        model = ScheduleTemplate
        fields = ['name', 'task_name', 'task_type', 'interval_days',
                  'warning_days_before', 'description']


class MaintenanceScheduleForm(forms.ModelForm):
    def __init__(self, *args, company=None, **kwargs):
        super().__init__(*args, **kwargs)
        if company:
            self.fields['piano'].queryset = Piano.objects.filter(company=company, is_active=True)

    class Meta:
        model = MaintenanceSchedule
        fields = ['piano', 'task_name', 'task_type', 'interval_days',
                  'warning_days_before', 'is_active']


class PartForm(forms.ModelForm):
    class Meta:
        model = Part
        fields = ['name', 'part_number', 'supplier', 'unit_cost',
                  'stock_quantity', 'reorder_threshold']


class WorkOrderLogWorkForm(forms.Form):
    """Form for logging work against a work order without completing it."""
    hours_worked = forms.DecimalField(
        max_digits=5, decimal_places=2, min_value=0,
        widget=forms.NumberInput(attrs={'step': '0.25', 'placeholder': '0.00'}),
    )
    work_performed = forms.CharField(
        widget=forms.Textarea(attrs={'rows': 3, 'placeholder': 'Describe the work performed…'}),
    )
    notes = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={'rows': 2, 'placeholder': 'Additional notes (optional)'}),
    )


class PhotoUploadForm(forms.Form):
    """Simple multi-photo upload form.
    Note: photos are handled directly from request.FILES in the view
    since Django's file widgets don't support 'multiple'. The template
    renders a raw <input type="file" multiple> element.
    """
    caption = forms.CharField(required=False, max_length=300)


class CompanySettingsForm(forms.ModelForm):
    class Meta:
        model = CompanySettings
        fields = ['company_name', 'address', 'phone', 'email', 'default_labor_rate']


class UserProfileForm(forms.ModelForm):
    """Let technicians update their own name and email."""
    class Meta:
        model = Technician
        fields = ['first_name', 'last_name', 'email']


class CompanyInvitationForm(forms.ModelForm):
    class Meta:
        model = CompanyInvitation
        fields = [
            'email', 'first_name', 'last_name',
            'role_admin', 'role_technician',
        ]


class CompanySwitcherForm(forms.Form):
    company_id = forms.IntegerField(min_value=1)


class MembershipRoleForm(forms.ModelForm):
    class Meta:
        model = CompanyMembership
        fields = ['role_admin', 'role_technician', 'is_active']


class PlatformCompanyInviteForm(forms.Form):
    company_name = forms.CharField(max_length=200)
    company_slug = forms.SlugField(
        max_length=80,
        required=False,
        help_text="Optional. Leave blank to generate from the company name.",
    )
    admin_first_name = forms.CharField(max_length=150, required=False)
    admin_last_name = forms.CharField(max_length=150, required=False)
    admin_email = forms.EmailField()
    admin_is_technician = forms.BooleanField(required=False, initial=True)

    def clean_company_slug(self):
        slug = self.cleaned_data.get('company_slug')
        name = self.cleaned_data.get('company_name', '')
        slug = slugify(slug or name)
        if not slug:
            raise forms.ValidationError('Enter a company name or slug.')
        if Company.objects.filter(slug=slug).exists():
            raise forms.ValidationError('A company with this slug already exists.')
        return slug

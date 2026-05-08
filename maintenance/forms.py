from django import forms
from .models import (
    Piano, WorkOrder, ConditionReading, ConditionLevel,
    MaintenanceSchedule, ScheduleTemplate, Part, TaskType,
    MaintenanceLog, Photo,
)


class PianoForm(forms.ModelForm):
    class Meta:
        model = Piano
        fields = [
            'name', 'make', 'model', 'serial_number',
            'piano_type', 'location', 'location_in_venue',
            'year_built', 'year_acquired',
            'tuning_interval_value', 'tuning_interval_unit',
            'regulation_interval_value', 'regulation_interval_unit',
            'voicing_interval_value', 'voicing_interval_unit',
            'cleaning_interval_value', 'cleaning_interval_unit',
            'notes',
        ]


class WorkOrderForm(forms.ModelForm):
    class Meta:
        model = WorkOrder
        fields = [
            'piano', 'order_type', 'task_type', 'priority',
            'assigned_tech', 'description', 'due_date',
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
    class Meta:
        model = MaintenanceSchedule
        fields = ['piano', 'task_name', 'task_type', 'interval_days',
                  'warning_days_before', 'is_active']


class PartForm(forms.ModelForm):
    class Meta:
        model = Part
        fields = ['name', 'part_number', 'supplier', 'unit_cost',
                  'stock_quantity', 'reorder_threshold']


class PhotoUploadForm(forms.Form):
    """Simple multi-photo upload form.
    Note: photos are handled directly from request.FILES in the view
    since Django's file widgets don't support 'multiple'. The template
    renders a raw <input type="file" multiple> element.
    """
    caption = forms.CharField(required=False, max_length=300)

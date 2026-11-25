from django.contrib import admin

from .models import Area, City, ServiceTag, SpecialityQuestion, Trade


class ServiceTagInline(admin.TabularInline):
    model = ServiceTag
    extra = 0
    fields = ("code", "label_ur", "label_en", "icon", "sort_order", "is_active")
    ordering = ("sort_order", "code")


@admin.register(Trade)
class TradeAdmin(admin.ModelAdmin):
    list_display = ("code", "label_en", "label_ur", "icon", "sort_order", "is_active")
    list_editable = ("sort_order", "is_active")
    list_filter = ("is_active",)
    search_fields = ("code", "label_en", "label_ur")
    inlines = [ServiceTagInline]


@admin.register(ServiceTag)
class ServiceTagAdmin(admin.ModelAdmin):
    list_display = ("code", "label_en", "label_ur", "trade", "icon", "sort_order", "is_active")
    list_editable = ("sort_order", "is_active")
    list_filter = ("trade", "is_active")
    search_fields = ("code", "label_en", "label_ur")
    list_select_related = ("trade",)


@admin.register(City)
class CityAdmin(admin.ModelAdmin):
    list_display = ("code", "label_en", "label_ur", "sort_order", "is_active")
    list_editable = ("sort_order", "is_active")
    search_fields = ("code", "label_en", "label_ur")


@admin.register(Area)
class AreaAdmin(admin.ModelAdmin):
    list_display = ("code", "label_en", "label_ur", "city", "kind", "sort_order", "is_active")
    list_editable = ("sort_order", "is_active")
    list_filter = ("city", "kind", "is_active")
    search_fields = ("code", "label_en", "label_ur")
    list_select_related = ("city",)


@admin.register(SpecialityQuestion)
class SpecialityQuestionAdmin(admin.ModelAdmin):
    list_display = ("code", "prompt_en", "choice_source", "min_selections", "max_selections", "sort_order", "is_active")
    list_filter = ("is_active",)

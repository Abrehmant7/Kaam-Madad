from rest_framework import serializers

from .models import Area, City, ServiceTag, SpecialityQuestion, Trade


class LabelsField(serializers.Field):
    """Bilingual label: {"ur": ..., "en": ...}."""

    def __init__(self, prefix: str = "label", **kwargs):
        self.prefix = prefix
        kwargs["source"] = "*"
        kwargs["read_only"] = True
        super().__init__(**kwargs)

    def to_representation(self, obj):
        return {"ur": getattr(obj, f"{self.prefix}_ur"), "en": getattr(obj, f"{self.prefix}_en")}


class TradeSerializer(serializers.ModelSerializer):
    labels = LabelsField()
    service_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Trade
        fields = ["code", "labels", "icon", "sort_order", "service_count"]


class ServiceTagSerializer(serializers.ModelSerializer):
    labels = LabelsField()
    trade = serializers.SlugRelatedField(slug_field="code", read_only=True)

    class Meta:
        model = ServiceTag
        fields = ["code", "trade", "labels", "icon", "sort_order"]


class CitySerializer(serializers.ModelSerializer):
    labels = LabelsField()

    class Meta:
        model = City
        fields = ["code", "labels", "sort_order"]


class AreaSerializer(serializers.ModelSerializer):
    labels = LabelsField()
    city = CitySerializer(read_only=True)
    centre = serializers.SerializerMethodField(help_text="Approximate public centre point, or null.")

    class Meta:
        model = Area
        fields = ["code", "city", "labels", "kind", "centre", "sort_order"]

    def get_centre(self, obj):
        if obj.centre_latitude is None:
            return None
        return {"latitude": float(obj.centre_latitude), "longitude": float(obj.centre_longitude), "approximate": True}


class SpecialityQuestionSerializer(serializers.ModelSerializer):
    prompt = serializers.SerializerMethodField()
    help = serializers.SerializerMethodField()
    selection = serializers.SerializerMethodField()

    class Meta:
        model = SpecialityQuestion
        fields = ["code", "prompt", "help", "selection"]

    def _trade(self) -> Trade:
        return self.context["trade"]

    def get_prompt(self, obj):
        trade = self._trade()
        return {
            "ur": obj.prompt_ur.replace("{trade}", trade.label_ur),
            "en": obj.prompt_en.replace("{trade}", trade.label_en),
        }

    def get_help(self, obj):
        trade = self._trade()
        return {
            "ur": obj.help_ur.replace("{trade}", trade.label_ur),
            "en": obj.help_en.replace("{trade}", trade.label_en),
        }

    def get_selection(self, obj):
        return {
            "multiple": obj.max_selections != 1,
            "min": obj.min_selections,
            "max": obj.max_selections,
            "choices_from": obj.choice_source,
        }

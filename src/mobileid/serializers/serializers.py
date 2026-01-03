from rest_framework import serializers

from ..models import Barcode, MobileID, Transaction


class BarcodeSerializer(serializers.ModelSerializer):
    class Meta:
        model = Barcode
        fields = [
            "id",
            "model_user",
            "time_created",
            "barcode_uuid",
            "barcode_type",
            "barcode",
            "profile_img",
            "profile_information_id",
            "profile_name",
            "has_profile",
            "get_profile_label",
        ]
        read_only_fields = ["id", "time_created", "barcode_uuid", "has_profile", "get_profile_label"]


class MobileIDSerializer(serializers.ModelSerializer):
    class Meta:
        model = MobileID
        fields = [
            "id",
            "model_user",
            "user_barcode",
            "user_mobile_id_server",
        ]
        read_only_fields = ["id"]


class TransactionSerializer(serializers.ModelSerializer):
    model_user_username = serializers.CharField(source="model_user.username", read_only=True)
    barcode_value = serializers.CharField(source="barcode_used.barcode", read_only=True)

    class Meta:
        model = Transaction
        fields = [
            "id",
            "model_user",
            "model_user_username",
            "barcode_used",
            "barcode_value",
            "time_used",
        ]
        read_only_fields = ["id", "time_used", "model_user_username", "barcode_value"]

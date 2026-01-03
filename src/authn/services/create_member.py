from typing import (
    Any,
)

from django.db import transaction

from ..models import *


class CreateMemberService:
    @staticmethod
    # database transaction decorator (disable for development)
    @transaction.atomic
    def create_member(
        # field for user
        username: str,
        password: str,
        first_name: str,
        last_name: str,
        # field for
    ) -> dict[str, Any]:
        """
        create a new member

        :arg
            username: str

        :return:
        """

        pass
